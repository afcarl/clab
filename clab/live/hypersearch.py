

def opt_crf():
    from clab.torch.urban_mapper import get_snapshot, urban_mapper_eval_dataset, PredictHarness  # NOQA
    from clab.torch.sseg_train import task_datasets, get_task, SSegInputsWrapper  # NOQA
    from clab import util
    import ubelt as ub

    # train_dpath = ub.truepath(
    #     '~/remote/aretha/data/work/urban_mapper/arch/unet/train/input_4214-yxalqwdk/solver_4214-yxalqwdk_unet_vgg_nttxoagf_a=1,n_ch=5,n_cl=3')
    # load_path = get_snapshot(train_dpath, epoch=202)

    datasets = task_datasets(get_task('urban_mapper_3d'))
    test_dataset = datasets['test']
    test_dataset.with_gt = False
    test_dataset.inputs.make_dumpsafe_names()
    test_dataset.center_inputs = test_dataset._original_urban_mapper_normalizer()
    test_dataset.tag = 'test'

    prob_folder = ub.truepath(
        '~/remote/aretha/data/work/urban_mapper/test/input_4224-rwyxarza/solver_4214-yxalqwdk_unet_vgg_nttxoagf_a=1,n_ch=5,n_cl=3/_epoch_00000202/log_probs')
    import glob

    subset = slice(300, 310)
    prob_paths = test_dataset.inputs.align(glob.glob(prob_folder + '/*.npz'))[subset]
    gt_paths = test_dataset.inputs.gt_paths[subset]
    im_paths = test_dataset.inputs.im_paths[subset]

    import numpy as np

    imgs = [util.imread(p) for p in ub.ProgIter(im_paths)]
    probs = [np.load(p)['arr_0'] for p in ub.ProgIter(prob_paths)]
    gts = [util.imread(p) for p in ub.ProgIter(gt_paths)]

    from .torch import filters
    # true = gts[4]

    import optml
    class_median_weights = test_dataset.class_weights()
    class_weights = class_median_weights / class_median_weights.sum()

    class CRFModel(optml.models.Model):
        __model_module__ = 'sklearn'  # hack
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_params(self, deep=False):
            return self.kwargs

        def fit(self, X, y=None):
            pass

        def predict(self, X):
            return [filters.crf_posterior(imgs[i], probs[i], **self.kwargs).argmax(axis=0) for i in ub.ProgIter(X, label='predicting')]

    def clf_score(y_true, y_pred):
        from .metrics import confusion_matrix, jaccard_score_from_confusion  # NOQA

        cfsn = np.zeros((3, 3))
        for i, pred in zip(y_true, y_pred):
            true = gts[i]
            cfsn += confusion_matrix(true.ravel(), pred.ravel(), [0, 1, 2])

        ious = jaccard_score_from_confusion(cfsn)
        weighted_miou = ((ious * class_weights)[0:2]).sum()
        return weighted_miou

    from optml.bayesian_optimizer import BayesianOptimizer

    model = CRFModel()

    params = [
        # w1 = kwargs.get('w1', 4)
        # w2 = kwargs.get('w2', 3)
        # sigma_alpha = kwargs.get('sigma_alpha', 100)
        # sigma_beta  = kwargs.get('sigma_beta', 3)
        # sigma_gamma = kwargs.get('sigma_gamma', 3)
        # n_iters = kwargs.get('n_iters', 10)

        optml.Parameter(name='w1',          param_type='integer', lower=1, upper=100),
        optml.Parameter(name='sigma_alpha', param_type='integer', lower=1, upper=150),
        optml.Parameter(name='sigma_beta',  param_type='integer', lower=1, upper=150),

        optml.Parameter(name='w2',          param_type='integer', lower=3, upper=3),
        optml.Parameter(name='sigma_gamma', param_type='integer', lower=3, upper=3),

        optml.Parameter(name='n_iters', param_type='integer', lower=10, upper=10),
        # optml.Parameter(name='param3', param_type='categorical', possible_values=['val1','val2','val3'])
    ]

    optimizer = BayesianOptimizer(model=model,
                                  hyperparams=params,
                                  eval_func=clf_score)
    # optimizer.model = model

    X_train = np.arange(len(prob_paths))  # dummy
    y_train = np.arange(len(X_train))

    # Add some good values to help out initial model
    seed_params = [
        # Best known so far
        {'n_iters': 10, 'sigma_alpha': 100, 'sigma_beta': 3, 'w1': 4, 'w2': 3, 'sigma_gamma': 3},

        {'n_iters': 10, 'sigma_alpha': 100, 'sigma_beta': 4, 'w1': 4, 'w2': 3, 'sigma_gamma': 3},
        {'n_iters': 10, 'sigma_alpha': 100, 'sigma_beta': 2, 'w1': 4, 'w2': 3, 'sigma_gamma': 3},

        {'n_iters': 10, 'sigma_alpha': 100, 'sigma_beta': 3, 'w1': 5, 'w2': 3, 'sigma_gamma': 3},
        {'n_iters': 10, 'sigma_alpha': 100, 'sigma_beta': 3, 'w1': 3, 'w2': 3, 'sigma_gamma': 3},

        {'n_iters': 10, 'sigma_alpha': 105, 'sigma_beta': 3, 'w1': 4, 'w2': 3, 'sigma_gamma': 3},
        {'n_iters': 10, 'sigma_alpha':  95, 'sigma_beta': 3, 'w1': 4, 'w2': 3, 'sigma_gamma': 3},

        {'n_iters': 10, 'sigma_alpha': 101, 'sigma_beta': 3, 'w1': 4, 'w2': 3, 'sigma_gamma': 3},
        {'n_iters': 10, 'sigma_alpha':  99, 'sigma_beta': 3, 'w1': 4, 'w2': 3, 'sigma_gamma': 3},

        {'n_iters': 10, 'sigma_alpha':  61, 'sigma_beta': 11, 'w1': 4, 'w2': 3, 'sigma_gamma': 3},

        {'n_iters': 10, 'sigma_alpha': 139, 'sigma_beta':  1, 'w1': 50, 'w2': 3, 'sigma_gamma': 3},
        {'n_iters': 10, 'sigma_alpha': 139, 'sigma_beta':  3, 'w1': 50, 'w2': 3, 'sigma_gamma': 3},
        {'n_iters': 10, 'sigma_alpha': 139, 'sigma_beta':  3, 'w1':  4, 'w2': 3, 'sigma_gamma': 3},
    ]

    seed_params = [
        # Best known so far
        {'n_iters':  5, 'sigma_alpha': 100, 'sigma_beta': 3, 'w1': 4, 'w2': 3, 'sigma_gamma': 3},
        {'n_iters': 20, 'sigma_alpha': 100, 'sigma_beta': 3, 'w1': 4, 'w2': 3, 'sigma_gamma': 3},
        # {'n_iters': 10, 'sigma_alpha': 100, 'sigma_beta': 3, 'w1': 4, 'w2': 1, 'sigma_gamma': 1},
        # {'n_iters': 10, 'sigma_alpha': 100, 'sigma_beta': 3, 'w1': 4, 'w2': 2, 'sigma_gamma': 2},
        # {'n_iters': 10, 'sigma_alpha': 100, 'sigma_beta': 3, 'w1': 4, 'w2': 4, 'sigma_gamma': 4},
    ]
    for seed in seed_params:
        print('seed = {}'.format(ub.repr2(seed, nl=0, precision=2)))
        print(optimizer._try_params(seed, X_train, y_train, X_train, y_train))

    bayes_best_params, bayes_best_model = optimizer.fit(X_train=X_train,
                                                        y_train=y_train,
                                                        n_iters=10,
                                                        verbose=True)

    names = [p.name for p in optimizer.hyperparams]
    names = ['w1', 'sigma_alpha', 'sigma_beta']
    xs = np.array([list(ub.take(params, names)) for score, params in optimizer.hyperparam_history])
    ys = np.array([score for score, params in optimizer.hyperparam_history])

    xs.T[0]
    import plottool as pt
    pt.qtensure()
    pt.plt.clf()
    for i in range(len(names)):
        pt.plt.plot(xs.T[i], ys, 'o', label=names[i])
    pt.plt.legend()


def opt_postprocess_boundary():
    import optml
    from clab import util
    from os.path import join, splitext, basename  # NOQA
    import glob
    import ubelt as ub
    import itertools as it
    import numpy as np
    from clab.live.urban_mapper import instance_fscore

    path = ub.truepath(
        '~/remote/aretha/data/work/urban_mapper2/test/input_4224-exkudlzu/'
        'solver_4214-guwsobde_unet_mmavmuou_eqnoygqy_a=1,c=RGB,n_ch=5,n_cl=4/'
        '_epoch_00000154/restiched/pred')
    mode_paths = sorted(glob.glob(path + '/*.png'))

    results = ub.odict()

    param_space = [
        # optml.Parameter(name='s', param_type='boolean'),
        optml.Parameter(name='w', param_type='boolean'),
        # optml.Parameter(name='k', param_type='integer', lower=1, upper=16),
        # optml.Parameter(name='d', param_type='integer', lower=1, upper=5),
        # optml.Parameter(name='n', param_type='integer', lower=1, upper=1),
    ]

    def itergrid():
        names = [p.name for p in param_space]
        for values in it.product(*map(iter, param_space)):
            yield ub.odict(zip(names, values))

    def instance_label2(pred_seg, w, s=True):
        import cv2

        mask = (pred_seg > 0).astype(np.uint8)
        seeds = cv2.connectedComponents((pred_seg == 1).astype(np.uint8), connectivity=4)[1]

        if not s:
            return cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)[1]
        else:
            if not w:
                return seeds
            else:
                topology = np.dstack([mask] * 3)
                seeds[mask == 0] = -1
                markers = cv2.watershed(topology, seeds.copy())
                markers[mask == 0] = 0
                markers[markers == -1] = 0

                n_ccs, cc_labels = cv2.connectedComponents(seeds.astype(np.uint8), connectivity=4)
                return cc_labels

    for params in itergrid():

        scores = []
        for pred_fpath in ub.ProgIter(mode_paths):
            gtl_fname = basename(pred_fpath).replace('.png', '_GTL.tif')
            gti_fname = basename(pred_fpath).replace('.png', '_GTI.tif')
            dsm_fname = basename(pred_fpath).replace('.png', '_DSM.tif')
            # bgr_fname = basename(pred_fpath).replace('.png', '_RGB.tif')
            gtl_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), gtl_fname)
            gti_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), gti_fname)
            dsm_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), dsm_fname)
            # bgr_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), bgr_fname)

            pred_seg = util.imread(pred_fpath)
            gti = util.imread(gti_fpath)
            gtl = util.imread(gtl_fpath)
            dsm = util.imread(dsm_fpath)
            # bgr = util.imread(bgr_fpath)

            pred = instance_label2(pred_seg, **params)

            uncertain = (gtl == 65)

            score = instance_fscore(gti, uncertain, dsm, pred)
            scores.append(score)

        res = np.array(scores).mean(axis=0)
        key = tuple(params.items())
        print('key = {!r}'.format(key))
        print('res = {!r}'.format(res))
        results[key] = res
