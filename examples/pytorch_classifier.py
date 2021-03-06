import torch
import torch.nn.functional as F
import torch_geometric.transforms as T
from torch_geometric.data import DataLoader, DenseDataLoader
import numpy as np
import argparse

from factnn.generator.pytorch.datasets import (
    ClusterDataset,
    DiffuseDataset,
    EventDataset,
)
from factnn.models.pytorch_models import PointNet2, PointNet2Segmenter

"""
from trains import Task

task = Task.init(project_name="IACT Classification", task_name="pytorch pointnet++", output_uri="/mnt/T7/")
task.name += " {}".format(task.id)


logger = task.get_logger()
"""


def test(args, model, device, test_loader):

    save_test_loss = []
    save_correct = []

    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data in test_loader:
            data = data.to(device)
            output = model(data)
            # sum up batch loss
            test_loss += F.nll_loss(output, data.y, reduction="sum").item()
            # get the index of the max log-probability
            pred = output.argmax(dim=1, keepdim=True)
            correct += pred.eq(data.y.view_as(pred)).sum().item()

            save_test_loss.append(test_loss)
            save_correct.append(correct)

    test_loss /= len(test_loader)

    print(
        "\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n".format(
            test_loss, correct, len(test_loader), 100.0 * correct / len(test_loader)
        )
    )


"""
    logger.report_histogram(
        title="Test Histogram",
        series="correct",
        iteration=1,
        values=save_correct,
        xaxis="Test",
        yaxis="Correct",
    )

    # Manually report test loss and correct as a confusion matrix
    matrix = np.array([save_test_loss, save_correct])
    logger.report_confusion_matrix(
        title="Confusion matrix",
        series="Test loss / correct",
        matrix=matrix,
        iteration=1,
    )
"""


def train(args, model, device, train_loader, optimizer, epoch):
    save_loss = []
    total_loss = 0
    model.train()
    for batch_idx, data in enumerate(train_loader):
        data = data.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = F.nll_loss(F.log_softmax(output, dim=-1), data.y)
        loss.backward()

        # save_loss.append(loss.item())

        optimizer.step()
        total_loss += loss.item()
        if batch_idx % args.log_interval == 0:
            print(
                "Train Epoch: {}\tLoss: {:.6f} \t Average loss {:.6f}".format(
                    epoch, loss.item(), total_loss / (batch_idx + 1)
                )
            )


"""           # Add manual scalar reporting for loss metrics
            logger.report_scalar(
                title="Training Loss {} - epoch".format(epoch),
                series="Loss",
                value=loss.item(),
                iteration=batch_idx,
            )
"""


def default_argument_parser():
    """
    Create a parser with some common arguments.

    Returns:
        argparse.ArgumentParser:
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--resume",
        action="store_true",
        help="whether to attempt to resume from the checkpoint directory",
    )
    parser.add_argument(
        "--augment",
        action="store_true",
        help="whether to augment input data, default False",
    )
    parser.add_argument(
        "--norm",
        action="store_true",
        help="whether to normalize point locations, default False",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=0,
        help="max number of sampled points, if > 0, default 0",
    )
    parser.add_argument(
        "--dataset", type=str, default="", help="path to dataset folder"
    )
    parser.add_argument(
        "--clean",
        type=str,
        default="no_clean",
        help="cleanliness value, one of 'no_clean', "
        "'clump5','clump10', 'clump15', 'clump20', "
        "'core5', 'core10', 'core15', 'core20'",
    )
    parser.add_argument("--lr", type=float, default=0.001, help="learning rate")
    parser.add_argument("--batch", type=int, default=32, help="batch size")
    parser.add_argument("--seed", type=int, default=1337, help="random seed for numpy")
    parser.add_argument("--epochs", type=int, default=200, help="number of epochs")
    parser.add_argument(
        "--log-interval",
        type=int,
        default=50,
        help="number of minibatches between logging",
    )

    return parser


if __name__ == "__main__":
    args = default_argument_parser().parse_args()
    np.random.seed(args.seed)
    num_classes = 2
    transforms = []
    if args.max_points > 0:
        transforms.append(T.FixedPoints(args.max_points))
    if args.augment:
        transforms.append(T.RandomRotate((-180, 180), axis=2))  # Rotate around z axis
        transforms.append(T.RandomFlip(0))  # Flp about x axis
        transforms.append(T.RandomFlip(1))  # Flip about y axis
        transforms.append(T.RandomTranslate(0.0001))  # Random jitter
    if args.norm:
        transforms.append(T.NormalizeScale())
    transform = T.Compose(transforms=transforms) if transforms else None
    train_dataset = EventDataset(
        args.dataset,
        "trainval",
        include_proton=True,
        task="separation",
        cleanliness=args.clean,
        pre_transform=None,
        transform=transform,
        balanced_classes=True,
        fraction=0.001
    )
    test_dataset = EventDataset(
        args.dataset,
        "test",
        include_proton=True,
        task="separation",
        cleanliness=args.clean,
        pre_transform=None,
        transform=transform,
        fraction=0.001
    )
    print(len(test_dataset))
    print(len(train_dataset))
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch,
        shuffle=True,
        num_workers=12,
    )
    print(next(iter(train_loader)))
    test_loader = DataLoader(
        test_dataset,
        batch_size=args.batch,
        shuffle=False,
        num_workers=12,
    )

    config = {
        "sample_ratio_one": 0.5,
        "sample_radius_one": 0.2,
        "sample_max_neighbor": 64,
        "sample_ratio_two": 0.25,
        "sample_radius_two": 0.4,
        "fc_1": 1024,
        "fc_1_out": 512,
        "fc_2_out": 256,
        "dropout": 0.5,
    }
    # config = task.connect_configuration(config)
    # task.connect_label_enumeration({"Gamma": 0, "Proton": 1})

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = PointNet2(num_classes, config).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    print("Model created")
    for epoch in range(args.epochs):
        train(args, model, device, train_loader, optimizer, epoch)
    test(args, model, device, test_loader)
