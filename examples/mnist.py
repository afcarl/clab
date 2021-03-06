# -*- coding: utf-8 -*-
"""
fit_harness takes your hyperparams and
applys standardized "state-of-the-art" training procedures

But everything is overwritable.
Experimentation and freedom to protype quickly is extremely important
We do our best not to get in the way, just performing a jumping off
point.

TODO:
    TrainingModes:
        [x] categorical
            see demos on:
                [x] MNIST
                [.] Cifar100
                [ ] ImageNet
                [ ] ...
        [ ] segmentation
            [ ] semantic
                [ ] CamVid
                [ ] CityScapes
                [ ] Diva
                [ ] UrbanMapper3D
                [ ] ...
            [ ] instance
                [ ] UrbanMapper3D
        [ ] tracking
            [ ] ...
        [ ] detection
            [ ] ...
            [ ] VOC2007
        [ ] identification
            [ ] 1-vs-all
            [ ] N-vs-all
            [ ] (1-vs-1) pairwise
            [ ] (N-vs-N)
            [ ] ...
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import ubelt as ub
import torch
import torch.nn
import torchvision  # NOQA
import torch.nn.functional as F
from torch import nn
import clab


class MnistNet(nn.Module):
    def __init__(self, n_channels=1, n_classes=10):
        super(MnistNet, self).__init__()
        self.conv1 = nn.Conv2d(n_channels, 10, kernel_size=5)
        self.conv2 = nn.Conv2d(10, 20, kernel_size=5)
        self.conv2_drop = nn.Dropout2d()
        self.fc1 = nn.Linear(320, 50)
        self.fc2 = nn.Linear(50, n_classes)

    def forward(self, x):
        x = F.relu(F.max_pool2d(self.conv1(x), 2))
        x = F.relu(F.max_pool2d(self.conv2_drop(self.conv2(x)), 2))
        x = x.view(-1, 320)
        x = F.relu(self.fc1(x))
        x = F.dropout(x, training=self.training)
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)


def train_mnist():
    """
    CommandLine:
        python examples/mnist.py

        python ~/code/clab/examples/mnist.py --gpu=2
        python ~/code/clab/examples/mnist.py
    """

    """
    TODO: IPython notebookize this demo

    So, you made a pytorch model
    You have a pytorch.Dataset
    How will you train your model?
    With FitHarness
    """
    import copy
    import numpy as np
    root = os.path.expanduser('~/data/mnist/')

    dry = ub.argflag('--dry')

    # Define your dataset
    transform = torchvision.transforms.Compose([
        torchvision.transforms.ToTensor(),
        torchvision.transforms.Normalize((0.1307,), (0.3081,))
    ])

    learn_dset = torchvision.datasets.MNIST(root, transform=transform,
                                            train=True, download=True)

    test_dset = torchvision.datasets.MNIST(root, transform=transform,
                                           train=True, download=True)

    train_dset = learn_dset
    vali_dset = copy.copy(learn_dset)

    # split the learning dataset into training and validation
    # take a subset of data
    # factor = .15
    factor = .15
    n_vali = int(len(learn_dset) * factor)
    learn_idx = np.arange(len(learn_dset))

    rng = np.random.RandomState(0)
    rng.shuffle(learn_idx)

    reduction = 1
    valid_idx = torch.LongTensor(learn_idx[:n_vali][::reduction])
    train_idx = torch.LongTensor(learn_idx[n_vali:][::reduction])

    def _torch_take(tensor, indices, axis):
        if torch.__version__.startswith('0.3'):
            TensorType = type(learn_dset.train_data)
        else:
            TensorType = learn_dset.train_data.type()
            TensorType = getattr(torch, TensorType.split('.')[1])
        return TensorType(tensor.numpy().take(indices, axis=axis))

    vali_dset.train_data   = _torch_take(learn_dset.train_data, valid_idx,
                                         axis=0)
    vali_dset.train_labels = _torch_take(learn_dset.train_labels, valid_idx,
                                         axis=0).long()

    train_dset.train_data   = _torch_take(learn_dset.train_data, train_idx,
                                          axis=0)
    train_dset.train_labels = _torch_take(learn_dset.train_labels, train_idx,
                                          axis=0).long()

    datasets = {
        'train': train_dset,
        'vali': vali_dset,
        'test': test_dset,
    }

    # Give the training dataset an input_id
    datasets['train'].input_id = 'mnist_' + ub.hash_data(train_idx.numpy())[0:8]
    del datasets['test']

    batch_size = 128
    n_classes = 10
    xpu = clab.xpu_device.XPU.from_argv(min_memory=300)

    if False:
        initializer = (clab.nninit.Pretrained, {
            'fpath': 'path/to/pretained/weights.pt'
        })
    else:
        initializer = (clab.nninit.KaimingNormal, {'nonlinearity': 'relu'})

    """
    # Here is the fit_harness magic.
    # This keeps track of your stuff
    """
    hyper = clab.hyperparams.HyperParams(
        model=(MnistNet, dict(n_channels=1, n_classes=n_classes)),
        # optimizer=torch.optim.Adam,
        optimizer=(torch.optim.SGD, {'lr': 0.01}),
        scheduler='ReduceLROnPlateau',
        criterion=torch.nn.CrossEntropyLoss,
        initializer=initializer,
        other={
            # record any other information that will be used to compare
            # different training runs here
            'n_classes': n_classes,
        }
    )

    loaders = ub.odict()
    data_kw = {'batch_size': batch_size}
    if xpu.is_gpu():
        data_kw.update({'num_workers': 6, 'pin_memory': True})
    for tag in ['train', 'vali', 'test']:
        if tag not in datasets:
            continue
        dset = datasets[tag]
        shuffle = tag == 'train'
        data_kw_ = data_kw.copy()
        if tag != 'train':
            data_kw_['batch_size'] = max(batch_size // 4, 1)
        loader = torch.utils.data.DataLoader(dset, shuffle=shuffle,
                                             **data_kw_)
        loaders[tag] = loader

    harn = clab.fit_harness.FitHarness(
        xpu=xpu, hyper=hyper, loaders=loaders, dry=dry,
        min_keys=['loss'], max_keys=['global_acc', 'class_acc'],
    )

    all_labels = np.arange(n_classes)

    @harn.add_batch_metric_hook
    def custom_metrics(harn, output, labels):
        # ignore_label = datasets['train'].ignore_label
        # labels = datasets['train'].task.labels
        label = labels[0]
        metrics_dict = clab.metrics._clf_metrics(output, label,
                                                 all_labels=all_labels)
        return metrics_dict

    workdir = ub.truepath('~/data/work/mnist/')
    train_dpath = harn.setup_dpath(workdir, hashed=True)
    print('train_dpath = {!r}'.format(train_dpath))

    if ub.argflag('--reset'):
        ub.delete(train_dpath)

    harn.run()

    # if False:
    #     import plottool as pt
    #     pt.qtensure()
    #     ims, gts = next(iter(harn.loaders['train']))
    #     pic = im_loaders.rgb_tensor_to_imgs(ims, norm=False)[0]
    #     pt.clf()
    #     pt.imshow(pic, norm=True, cmap='viridis', data_colorbar=True)

    #     with pt.RenderingContext() as render:
    #         tensor_data = datasets['train'][0][0][None, :]
    #         pic = im_loaders.rgb_tensor_to_imgs(tensor_data, norm=False)[0]
    #         pt.figure(fnum=1, doclf=True)
    #         pt.imshow(pic, norm=True, cmap='viridis', data_colorbar=True,
    #                   fnum=1)
    #     render.image

if __name__ == '__main__':
    r"""
    CommandLine:
        python examples/mnist.py
    """
    train_mnist()
