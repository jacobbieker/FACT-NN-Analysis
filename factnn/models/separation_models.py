from tensorflow.keras.layers import (
    Dense,
    Dropout,
    Flatten,
    ConvLSTM2D,
    Conv3D,
    MaxPooling3D,
)
from tensorflow.keras.models import Sequential

from factnn.models.base_model import BaseModel


class SeparationModel(BaseModel):
    """
    Generates and returns a Keras model to separate two types of events, normally gamma and hadron events
    """

    def init(self):
        self.model_type = "Separation"
        self.auc = 0.0
        if self.name is None:
            self.name = (
                self.model_type
                + "_"
                + str(self.num_lstm)
                + "LSTM_"
                + str(self.num_conv3d)
                + "Conv3D_"
                + str(self.num_fc)
                + "FC"
                + ".hdf5"
            )

    def create(self):
        """
        Creates a Sequential Keras model based on the configuration passed
        :return:
        """
        model = Sequential()

        if self.num_lstm > 0:
            model.add(
                ConvLSTM2D(
                    self.neurons[0],
                    kernel_size=self.kernel_lstm,
                    strides=self.strides_lstm,
                    padding="same",
                    input_shape=self.shape,
                    activation=self.activation,
                    dropout=self.conv_dropout,
                    recurrent_dropout=self.lstm_dropout,
                    recurrent_activation="hard_sigmoid",
                    return_sequences=True,
                )
            )
            if self.pooling:
                model.add(MaxPooling3D())
            for i in range(self.num_lstm - 1):
                model.add(
                    ConvLSTM2D(
                        self.neurons[i + 1],
                        kernel_size=self.kernel_lstm,
                        strides=self.strides_lstm,
                        padding="same",
                        activation=self.activation,
                        dropout=self.conv_dropout,
                        recurrent_dropout=self.lstm_dropout,
                        recurrent_activation="hard_sigmoid",
                        return_sequences=True,
                    )
                )
                if self.pooling:
                    model.add(MaxPooling3D())

            for i in range(self.num_conv3d):
                model.add(
                    Conv3D(
                        self.neurons[self.num_lstm + i],
                        kernel_size=self.kernel_conv3d,
                        strides=self.strides_conv3d,
                        padding="same",
                        activation=self.activation,
                    )
                )
                if self.pooling:
                    model.add(MaxPooling3D())

        else:
            model.add(
                Conv3D(
                    self.neurons[0],
                    input_shape=self.shape,
                    kernel_size=1,
                    strides=1,
                    padding="same",
                    activation=self.activation,
                )
            )
            if self.pooling:
                model.add(MaxPooling3D())
            for i in range(self.num_conv3d - 1):
                model.add(
                    Conv3D(
                        self.neurons[i + 1],
                        kernel_size=self.kernel_conv3d,
                        strides=self.strides_conv3d,
                        padding="same",
                        activation=self.activation,
                    )
                )
                if self.pooling:
                    model.add(MaxPooling3D())

        model.add(Flatten())

        for i in range(self.num_fc):
            model.add(
                Dense(
                    self.neurons[self.num_lstm + self.num_conv3d + i],
                    activation=self.activation,
                )
            )
            model.add(Dropout(self.fc_dropout))

        # Final Dense layer
        model.add(Dense(2, activation="softmax"))
        model.compile(
            optimizer="adam", loss="categorical_crossentropy", metrics=["acc"]
        )

        self.model = model

    def save(self, name=None):
        if name is None:
            self.model.save(self.name)
        else:
            self.model.save(name)
