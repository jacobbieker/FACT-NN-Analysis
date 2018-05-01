from keras import backend as K
import h5py
from fact.io import read_h5py
import yaml
import os
import keras
import numpy as np
from keras.models import Sequential
from keras.layers import Dense, Dropout, Activation, Conv1D, Flatten, Reshape, BatchNormalization, Conv2D, MaxPooling2D
from fact.coordinates.utils import horizontal_to_camera

architecture = 'intel'

if architecture == 'manjaro':
    base_dir = '/run/media/jacob/WDRed8Tb1'
    thesis_base = '/run/media/jacob/SSD/Development/thesis'
else:
    base_dir = '/projects/sventeklab/jbieker'
    thesis_base = base_dir + '/git-thesis/thesis'

# Hyperparameters

batch_sizes = [4, 8, 16, 32, 64, 128, 256]
patch_sizes = [(3, 3), (5, 5)]
dropout_layers = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
num_conv_layers = [0,1,2,3,4,5]
num_dense_layers = [0,1,2,3,4,5]
num_conv_neurons = [8, 16, 32, 64, 128]
num_dense_neuron = [64, 128, 256, 512, 1024]
num_pooling_layers = [0,1]
number_of_training = 640000*(0.6)
number_of_testing = 640000*(0.2)
number_validate = 640000*(0.2)
optimizers = ['rmsprop', 'sgd', 'adam']
activations = ['relu', 'linear', 'sigmoid'] # Only for the last layer

path_mc_images = base_dir + "/FACTSources/Rebinned_5_Diffuse_Preprocessed_Images.h5"
for batch_size in batch_sizes:
    for patch_size in patch_sizes:
        for dropout_layer in dropout_layers:
            for num_conv in num_conv_layers:
                for num_dense in num_dense_layers:
                    for num_pooling_layer in num_pooling_layers:
                        for conv_neurons in num_conv_neurons:
                            for dense_neuron in num_dense_neuron:
                                for activation in activations:
                                    for optimizer in optimizers:
                                        try:
                                            model_name = base_dir + "/MC_disp_b" + str(batch_size) +"_p_" + str(patch_size) + "_drop_" + str(dropout_layer) \
                                                         + "_conv_" + str(num_conv) + "_pool_" + str(num_pooling_layer) + "_act_" + \
                                                         str(activation) + "_denseN_" + str(dense_neuron) + "_convN_" + \
                                                         str(conv_neurons) + "_opt_" + str(optimizer) + ".h5"
                                            if not os.path.isfile(model_name):
                                                model_checkpoint = keras.callbacks.ModelCheckpoint(model_name, monitor='val_loss', verbose=0,
                                                                                                   save_best_only=True, save_weights_only=False, mode='auto', period=1)
                                                early_stop = keras.callbacks.EarlyStopping(monitor='val_loss', min_delta=0, patience=4, verbose=0, mode='auto')
                                                def metaYielder():
                                                    with h5py.File(path_mc_images, 'r') as f:
                                                        keys = list(f.keys())
                                                        events = []
                                                        for key in keys:
                                                            events.append(len(f[key]))

                                                    gamma_anteil = events[0]/np.sum(events)
                                                    gamma_count = int(round(number_of_training*gamma_anteil))

                                                    return gamma_anteil, gamma_count


                                                with h5py.File(path_mc_images, 'r') as f:
                                                    gamma_anteil, gamma_count = metaYielder()
                                                    # Get some truth data for now, just use Crab images
                                                    images = f['Image'][-(gamma_anteil*number_of_testing):-1]
                                                    images_source_zd = f['Zd_deg'][-(gamma_anteil*number_of_testing):-1]
                                                    images_source_az = f['Az_deg'][-(gamma_anteil*number_of_testing):-1]
                                                    images_point_az = f['Pointing_Az'][-(gamma_anteil*number_of_testing):-1]
                                                    images_point_zd = f['Pointing_Zd'][-(gamma_anteil*number_of_testing):-1]
                                                    source = horizontal_to_camera(
                                                        az=images_source_az, zd=images_source_zd,
                                                        az_pointing=images_point_az, zd_pointing=images_point_zd
                                                    )
                                                    del images_point_zd
                                                    del images_point_az
                                                    del images_source_zd
                                                    del images_source_az

                                                    y = images
                                                    y_label = source
                                                    print("Finished getting data")


                                                def batchYielder():
                                                    gamma_anteil, gamma_count = metaYielder()
                                                    while True:
                                                        with h5py.File(path_mc_images, 'r') as f:
                                                            # Get some truth data for now, just use Crab images
                                                            items = list(f.items())[1][1].shape[0]
                                                            items = items - number_of_testing
                                                            batch_num = 0
                                                            # Roughly 5.6 times more simulated Gamma events than proton, so using most of them
                                                            while (number_of_training) * (batch_num + 1) < items:
                                                                gamma_anteil, gamma_count = metaYielder()
                                                                # Get some truth data for now, just use Crab images
                                                                images = f['Image'][-(gamma_anteil*number_of_training):-1]
                                                                images_source_zd = f['Zd_deg'][-(gamma_anteil*number_of_training):-1]
                                                                images_source_az = f['Az_deg'][-(gamma_anteil*number_of_training):-1]
                                                                images_point_az = f['Pointing_Az'][-(gamma_anteil*number_of_training):-1]
                                                                images_point_zd = f['Pointing_Zd'][-(gamma_anteil*number_of_training):-1]
                                                                source = horizontal_to_camera(
                                                                    az=images_source_az, zd=images_source_zd,
                                                                    az_pointing=images_point_az, zd_pointing=images_point_zd
                                                                )
                                                                del images_point_zd
                                                                del images_point_az
                                                                del images_source_zd
                                                                del images_source_az

                                                                x = images
                                                                x_label = source
                                                                batch_num += 1
                                                                yield (x, x_label)

                                                gamma_anteil, gamma_count = metaYielder()
                                                # Make the model
                                                model = Sequential()

                                                # Base Conv layer
                                                model.add(Conv2D(conv_neurons, kernel_size=patch_size, strides=(1, 1),
                                                                 activation='relu', padding='same',
                                                                 input_shape=(75, 75, 1)))

                                                for i in range(num_conv):
                                                    model.add(Conv2D(conv_neurons, patch_size, strides=(1, 1), activation='relu', padding='same'))
                                                    if num_pooling_layer == 1:
                                                        model.add(MaxPooling2D(pool_size=(2, 2), padding='same'))
                                                    model.add(Dropout(dropout_layer))

                                                #model.add(Flatten())

                                                # Now do the dense layers
                                                for i in range(num_dense):
                                                    model.add(Dense(dense_neuron, activation='relu'))
                                                    model.add(Dropout(dropout_layer))

                                                # Final Dense layer
                                                # 2 so have one for x and one for y
                                                model.add(Dense(2, activation=activation))
                                                model.compile(optimizer=optimizer, loss='mse', metrics=['mse'])
                                                model.fit_generator(generator=batchYielder(), steps_per_epoch=np.floor(((number_of_training / batch_size))), epochs=100,
                                                                    verbose=2, validation_data=(y, y_label), callbacks=[early_stop, model_checkpoint])

                                        except Exception as e:
                                            print(e)
                                            pass