import os.path as osp
import pickle
import numpy as np
from zlib import crc32

import torch
from torch_geometric.data import Dataset
from torch_geometric.data import Data

from photon_stream.representations import list_of_lists_to_raw_phs, raw_phs_to_point_cloud
from photon_stream.geometry import GEOMETRY

from factnn.utils.augment import euclidean_distance, true_sign


class EventDataset(Dataset):

    def __init__(self, root, split="trainval", include_proton=True, task="Separation", transform=None,
                 pre_transform=None):
        """
        :param task: Either 'Separation', 'Energy', or 'Disp'
        :param split: Splits to include, either 'train', 'val', 'test', or 'trainval' for training, validation, test, or training and validation sets
        :param root: Root directory for the dataset
        :param include_proton: Whether to include proton events or not
        """
        self.processed_filenames = []
        self.task = task
        self.split = split
        self.include_proton = include_proton
        super(EventDataset, self).__init__(root, transform, pre_transform)

    @property
    def raw_file_names(self):
        return np.loadtxt("/home/jacob/Development/factnn/raw_names.txt", dtype=str)

    @property
    def processed_file_names(self):
        return self.processed_filenames

    def download(self):
        pass

    def process(self):
        i = 0

        used_paths = split_data(self.raw_paths)[self.split]

        for raw_path in used_paths:
            if not self.include_proton and "proton" in raw_path:
                continue
            # load the pickled file from the disk
            if osp.exists(osp.join(self.processed_dir, self.split, f"data_{i}.pt")):
                self.processed_filenames.append(f"data_{i}.pt")
            else:
                with open(raw_path, "rb") as pickled_event:
                    print(raw_path)
                    event_data, data_format, features, feature_cluster = pickle.load(pickled_event)
                    # Convert List of List to Point Cloud, then truncation is simply cutting in the z direction
                    event_photons = event_data[data_format["Image"]]
                    event_photons = list_of_lists_to_raw_phs(event_photons)
                    point_cloud = np.asarray(raw_phs_to_point_cloud(event_photons,
                                                                    cx=GEOMETRY.x_angle,
                                                                    cy=GEOMETRY.y_angle))
                    # Read data from `raw_path`.
                    data = Data(pos=point_cloud)  # Just need x,y,z ignore derived features
                    if "gamma" in raw_path:
                        data.event_type = torch.tensor(0, dtype=torch.int8)
                    elif "proton" in raw_path:
                        data.event_type = torch.tensor(1, dtype=torch.int8)
                    else:
                        print("No Event Type")
                        continue
                    data.energy = torch.tensor(event_data[data_format["Energy"]], dtype=torch.float)
                    if self.pre_filter is not None and not self.pre_filter(data):
                        continue

                    if self.pre_transform is not None:
                        data = self.pre_transform(data)

                    torch.save(data, osp.join(self.processed_dir, self.split, 'data_{}.pt'.format(i)))
                    self.processed_filenames.append('data_{}.pt'.format(i))
                    i += 1

    def len(self):
        return len(self.processed_file_names)

    def get(self, idx):
        data = torch.load(osp.join(self.processed_dir, self.split, self.processed_file_names[idx]))
        if self.task == "Energy":
            data.y = data.energy
        else:
            data.y = data.event_type
        return data


class DiffuseDataset(Dataset):

    def __init__(self, root, split="trainval", transform=None, pre_transform=None):
        """
        EventFile Dataloader for specifically Disp calculations,
        only using the diffuse gamma sources that have the extra information

        Use EventFileDataset for Energy and Separation tasks

        :param num_points: The number of points to have, either using points multiple times, or subselecting from the total points
        """
        self.processed_filenames = []
        self.split = split
        super(DiffuseDataset, self).__init__(root, transform, pre_transform)

    @property
    def raw_file_names(self):
        return np.loadtxt("/home/jacob/Development/factnn/raw_names.txt", dtype=str)

    @property
    def processed_file_names(self):
        return self.processed_filenames

    def download(self):
        pass

    def process(self):
        i = 0

        used_paths = split_data(self.raw_paths)[self.split]
        # load the pickled file from the disk
        if osp.exists(osp.join(self.processed_dir, self.split, f"data_{i}.pt")):
            self.processed_filenames.append(f"data_{i}.pt")
        else:
            for raw_path in used_paths:
                # Checks that file is not 0
                with open(raw_path, "rb") as pickled_event:
                    print(raw_path)
                    event_data, data_format, features, feature_cluster = pickle.load(pickled_event)
                    # Convert List of List to Point Cloud, then truncation is simply cutting in the z direction
                    event_photons = event_data[data_format["Image"]]
                    event_photons = list_of_lists_to_raw_phs(event_photons)
                    point_cloud = np.asarray(raw_phs_to_point_cloud(event_photons,
                                                                    cx=GEOMETRY.x_angle,
                                                                    cy=GEOMETRY.y_angle))
                    # Read data from `raw_path`.
                    data = Data(pos=point_cloud)  # Just need x,y,z ignore derived features
                    data.y = torch.tensor(true_sign(event_data[data_format['Source_X']],
                                                    event_data[data_format['Source_Y']],
                                                    event_data[data_format['COG_X']],
                                                    event_data[data_format['COG_Y']],
                                                    event_data[data_format['Delta']]) * euclidean_distance(
                        event_data[data_format['Source_X']],
                        event_data[data_format['Source_Y']],
                        event_data[data_format['COG_X']],
                        event_data[data_format['COG_Y']]),
                                          dtype=torch.float16)
                    if self.pre_filter is not None and not self.pre_filter(data):
                        continue

                    if self.pre_transform is not None:
                        data = self.pre_transform(data)

                    torch.save(data, osp.join(self.processed_dir, self.split, 'data_{}.pt'.format(i)))
                    self.processed_filenames.append('data_{}.pt'.format(i))
                    i += 1

    def len(self):
        return len(self.processed_file_names)

    def get(self, idx):
        data = torch.load(osp.join(self.processed_dir, self.split, self.processed_file_names[idx]))
        return data


class ClusterDataset(Dataset):

    def __init__(self, root, uncleaned_root, split="trainval", transform=None,
                 pre_transform=None):
        """

        Dataset for working on clustering datapoints, such as a replacement for DBSCAN algorithm.
        :param uncleaned_root: Root of files, with same names, that do not have the DBSCAN cleaned output
        :param split: Splits to include, either 'train', 'val', 'test', or 'trainval' for training, validation, test, or training and validation sets
        :param root: Root directory for the dataset, holding the files with the "cleaned" files
        """
        self.processed_filenames = []
        self.split = split
        self.uncleaned_root = uncleaned_root
        super(ClusterDataset, self).__init__(root, transform, pre_transform)

    @property
    def raw_file_names(self):
        return np.loadtxt("/home/jacob/Development/factnn/raw_names.txt", dtype=str)

    @property
    def processed_file_names(self):
        return self.processed_filenames

    def download(self):
        pass

    def process(self):
        i = 0

        used_paths = split_data(self.raw_file_names)[self.split]

        for base_path in used_paths:
            raw_path = osp.join(self.raw_dir, base_path)
            uncleaned_path = osp.join(self.uncleaned_root, base_path)
            # load the pickled file from the disk
            if osp.exists(osp.join(self.processed_dir, self.split, f"data_{i}.pt")):
                self.processed_filenames.append(f"data_{i}.pt")
            else:
                with open(raw_path, "rb") as pickled_event:
                    with open(uncleaned_path, 'rb') as pickled_original:
                        print(raw_path)
                        event_data, data_format, features, feature_cluster = pickle.load(pickled_event)
                        uncleaned_data, _, _, _ = pickle.load(pickled_original)
                        uncleaned_photons = uncleaned_data[data_format["Image"]]
                        uncleaned_photons = list_of_lists_to_raw_phs(uncleaned_photons)
                        uncleaned_cloud = np.asarray(raw_phs_to_point_cloud(uncleaned_photons,
                                                                            cx=GEOMETRY.x_angle,
                                                                            cy=GEOMETRY.y_angle))
                        # Convert List of List to Point Cloud, then truncation is simply cutting in the z direction
                        event_photons = event_data[data_format["Image"]]
                        event_photons = list_of_lists_to_raw_phs(event_photons)
                        point_cloud = np.asarray(raw_phs_to_point_cloud(event_photons,
                                                                        cx=GEOMETRY.x_angle,
                                                                        cy=GEOMETRY.y_angle))
                        # Read data from `raw_path`.
                        point_values = np.isclose(uncleaned_cloud, point_cloud) # Get a mask for which points are in it
                        print(point_values)
                        print(point_values.shape)
                        data = Data(pos=uncleaned_cloud, y=point_values)  # Just need x,y,z ignore derived features
                        if self.pre_filter is not None and not self.pre_filter(data):
                            continue

                        if self.pre_transform is not None:
                            data = self.pre_transform(data)

                        torch.save(data, osp.join(self.processed_dir, self.split, 'data_{}.pt'.format(i)))
                        self.processed_filenames.append('data_{}.pt'.format(i))
                        i += 1

    def len(self):
        return len(self.processed_file_names)

    def get(self, idx):
        data = torch.load(osp.join(self.processed_dir, self.split, self.processed_file_names[idx]))
        return data


# Function to check test set's identifier.
def test_set_check(identifier, test_ratio):
    return crc32(np.int64(identifier)) & 0xffffffff < test_ratio * 2 ** 32


# Function to split train/test
def split_train_test_by_id(data, test_ratio):
    in_test_set = np.asarray([test_set_check(crc32(str(x).encode()), test_ratio) for x in data])
    return data[~in_test_set], data[in_test_set]


def split_data(paths, val_split=0.2, test_split=0.2):
    """
    Split up the data and return which images should go to which train, test, val directory
    :param paths: The paths to do the splitting on
    :param test_split: Fraction of the data for the test set. the validation set is rolled into the test set.
    :param val_split: Fraction of data in validation set
    :return: A dict containing which images go to which directory
    """

    print(len(paths))
    train, test = split_train_test_by_id(np.asarray(paths), val_split + test_split)
    val, test = split_train_test_by_id(test, val_split)
    print(len(train))
    print(len(val))
    print(len(test))
    return {"train": train,
            "val": val,
            "trainval": train + val,
            "test": test}