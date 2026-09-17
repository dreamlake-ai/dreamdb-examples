"""One shared tiny model for original PNG and training-ready input paths."""


def make_model(sensor_dim):
    import torch
    from torch import nn

    class Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.image = nn.Sequential(
                nn.Conv2d(12, 8, 5, stride=2),
                nn.ReLU(),
                nn.Conv2d(8, 16, 3, stride=2),
                nn.ReLU(),
                nn.AdaptiveAvgPool2d(1),
                nn.Flatten(),
            )
            self.head = nn.Sequential(
                nn.Linear(16 + 4 * sensor_dim, 32), nn.ReLU(), nn.Linear(32, 1)
            )

        def forward(self, images, sensors):
            return self.head(torch.cat([self.image(images), sensors.flatten(1)], dim=1))

    return Model()
