# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
import torch
import glob
import numpy as np  # NOQA
import ubelt as ub
import os  # NOQA
from os.path import join, splitext, basename  # NOQA
from clab import util
from clab.torch import xpu_device
from clab.torch import models
from clab.util import imutil
from clab.torch.fit_harness import get_snapshot


def urban_mapper_eval_dataset(boundary=True, arch=None):
    from clab.live.urban_train import get_task, SSegInputsWrapper
    from clab import preprocess
    task = get_task('urban_mapper_3d', boundary=boundary, arch=arch)
    eval_fullres = task.load_fullres_inputs('testing')
    datadir = ub.ensuredir((task.workdir, 'eval_data'))
    prep = preprocess.Preprocessor(datadir)
    prep.part_config['overlap'] = .75
    eval_part1_scale = prep.make_parts(eval_fullres, scale=1, clear=0)
    # from clab.profiler import profile_onthefly
    # profile_onthefly(prep.make_parts)(eval_fullres, scale=1, clear=0)

    eval_dataset = SSegInputsWrapper(eval_part1_scale, task, colorspace='RGB')
    eval_dataset.with_gt = False
    eval_dataset.inputs.make_dumpsafe_names()
    eval_dataset.fullres = eval_fullres
    eval_dataset.tag = 'eval'

    return eval_dataset


def eval_contest_testset():
    """
    hacked together script to get the testing data and run prediction for submission

    train_dpath = ub.truepath('~/remote/aretha/data/work/urban_mapper2/arch/unet2/train/input_4214-guwsobde/solver_4214-guwsobde_unet2_mmavmuou_tqynysqo_a=1,c=RGB,n_ch=5,n_cl=4')

    # Submission URL
    # https://community.topcoder.com/longcontest/

    CommandLine:
        python -m clab.live.urban_mapper eval_contest_testset --arch=unet2 --combine

    Script:
        >>> eval_contest_testset()

    """
    MODE = 'DENSE'
    MODE = 'UNET6CH'
    if MODE == 'DENSE':
        arch = 'dense_unet'
        train_dpath = ub.truepath(
            '~/remote/aretha/data/work/urban_mapper4/arch/dense_unet/train/input_25800-phpjjsqu/'
            'solver_25800-phpjjsqu_dense_unet_mmavmuou_zeosddyf_a=1,c=RGB,n_ch=6,n_cl=4')
        epoch = 26
        if epoch == 26:
            params = {'mask_thresh': 0.7870, 'min_seed_size': 85.1641, 'min_size': 64.0634, 'seed_thresh': 0.4320}  # .902
            pass
        use_aux_diff = True
        boundary = True
    elif MODE == 'UNET6CH':
        arch = 'unet2'
        train_dpath = ub.truepath(
            '~/remote/aretha/data/work/urban_mapper2/arch/unet2/train/input_25800-hemanvft/'
            'solver_25800-hemanvft_unet2_mmavmuou_stuyuerd_a=1,c=RGB,n_ch=6,n_cl=4')
        # epoch = 34
        # epoch = None
        boundary = True
        use_aux_diff = True
        # params = {'seed_thresh': 0.6573, 'mask_thresh': 0.8338, 'min_seed_size': 25, 'min_size': 38,}
        # params = {'mask_thresh': 0.8367, 'seed_thresh': 0.4549, 'min_seed_size': 97, 'min_size': 33}
        # params = {'mask_thresh': 0.7664, 'seed_thresh': 0.4090, 'min_seed_size': 48, 'min_size': 61}
        # if epoch == 34:
        #     params = {'mask_thresh': 0.8427, 'seed_thresh': 0.4942, 'min_seed_size': 56, 'min_size': 82}  # 0.9091

        # if epoch == 36:
        #     # TODO: FIND CORRECT PARAMS FOR THIS EPOCH
        #     params = {'mask_thresh': 0.8427, 'seed_thresh': 0.4942, 'min_seed_size': 56, 'min_size': 82}

        train_dpath = '/home/local/KHQ/jon.crall/data/work/urban_mapper2/arch/unet2/train/input_52200-fqljkqlk/solver_52200-fqljkqlk_unet2_ybypbjtw_smvuzfkv_a=1,c=RGB,n_ch=6,n_cl=4'
        epoch = 0
        if epoch == 0:
            params = {'mask_thresh': 0.6666, 'min_seed_size': 81, 'min_size': 13, 'seed_thresh': 0.4241}  # best on more data
            params = {'mask_thresh': 0.7870, 'min_seed_size': 85, 'min_size': 64, 'seed_thresh': 0.4320}  # 0.9169 (vali seen in training)

        epoch = 5

        epoch = 9
        if epoch == 9:
            # just guessing
            params = {'mask_thresh': 0.6666, 'min_seed_size': 81, 'min_size': 13, 'seed_thresh': 0.4241}
    else:
        raise KeyError(MODE)

    load_path = get_snapshot(train_dpath, epoch=epoch)

    eval_dataset = urban_mapper_eval_dataset(boundary=boundary, arch=arch)
    eval_dataset.use_aux_diff = use_aux_diff
    eval_dataset.with_gt = False
    eval_dataset.inputs.make_dumpsafe_names()
    eval_dataset.tag = 'eval'

    pharn = PredictHarness(eval_dataset)
    eval_dataset.center_inputs = pharn.load_normalize_center(train_dpath)
    pharn.hack_dump_path(load_path)

    prob_paths = glob.glob(join(pharn.test_dump_dpath, 'stitched', 'probs', '*.h5'))
    prob1_paths = glob.glob(join(pharn.test_dump_dpath, 'stitched', 'probs1', '*.h5'))
    if len(prob_paths) == 0:
        pharn.load_snapshot(load_path)
        pharn.run()

    def compact_idstr(dict_):
        short_keys = util.shortest_unique_prefixes(dict_.keys())
        short_dict = ub.odict(sorted(zip(short_keys, dict_.values())))
        idstr = ub.repr2(short_dict, nobr=1, itemsep='', si=1, nl=0,
                         explicit=1)
        return idstr

    def two_channel_prob_version():
        task = eval_dataset.task
        # prob_paths = pharn._restitch_type('probs', blend='avew', force=False)
        # prob1_paths = pharn._restitch_type('probs1', blend='avew', force=False)
        prob_paths = glob.glob(join(pharn.test_dump_dpath, 'stitched', 'probs', '*.h5'))
        prob1_paths = glob.glob(join(pharn.test_dump_dpath, 'stitched', 'probs1', '*.h5'))

        def seeded_predictions(**params):
            # Convert to submission output format
            seed_thresh = params.pop('seed_thresh')
            mask_thresh = params.pop('mask_thresh')

            for path, path1 in ub.ProgIter(list(zip(prob_paths, prob1_paths))):
                probs = util.read_arr(path)
                seed_probs = probs[:, :, task.classname_to_id['inner_building']]
                seed = (seed_probs > seed_thresh).astype(np.uint8)

                probs1 = util.read_arr(path1)
                mask_probs = probs1[:, :, 1]
                mask = (mask_probs > mask_thresh).astype(np.uint8)

                pred = seeded_instance_label(seed, mask, **params)
                tile_id = splitext(basename(path))[0]
                yield tile_id, pred

        lines = []
        for tile_id, pred in seeded_predictions(**params):
            (width, height), runlen = imutil.run_length_encoding(pred)
            lines.append(tile_id)
            lines.append('{},{}'.format(width, height))
            lines.append(','.join(list(map(str, runlen))))

        text = '\n'.join(lines)
        post_idstr = 'seeded_' + compact_idstr(params)
        mode = 'prob'
        suffix = '_'.join(pharn.test_dump_dpath.split('/')[-2:]) + '_' + mode + '_' + post_idstr
        fpath = join(pharn.test_dump_dpath, 'urban_mapper_test_pred_' + suffix + '.txt')
        print('fpath = {!r}'.format(fpath))
        ub.writeto(fpath, text)
        print(ub.codeblock(
            '''
            # Execute on remote computer
            cd ~/Dropbox/TopCoder
            rsync aretha:{fpath} .

            # submit here: https://community.topcoder.com/longcontest/
            '''
        ).format(fpath=fpath))
    two_channel_prob_version()

    # # mode = 'pred_crf'
    # def two_channel_version():
    #     task = eval_dataset.task
    #     restitched_pred0 = pharn._restitch_type('pred', blend='vote')
    #     restitched_pred1 = pharn._restitch_type('pred1', blend='vote')
    #     pharn._restitch_type('blend_pred', blend=None)
    #     pharn._restitch_type('blend_pred1', blend=None)

    #     out_fpaths = unet2_instance_restitch(restitched_pred0, restitched_pred1, task)

    #     lines = []
    #     for fpath in sorted(out_fpaths):
    #         pred = imutil.imread(fpath)
    #         import cv2
    #         cc_labels = cv2.connectedComponents(pred, connectivity=4)[1]

    #         fname = splitext(basename(fpath))[0]
    #         (width, height), runlen = imutil.run_length_encoding(cc_labels)

    #         lines.append(fname)
    #         lines.append('{},{}'.format(width, height))
    #         lines.append(','.join(list(map(str, runlen))))

    #     text = '\n'.join(lines)
    #     post_idstr = 'dualout'
    #     mode = 'pred'
    #     suffix = '_'.join(pharn.test_dump_dpath.split('/')[-2:]) + '_' + mode + '_' + post_idstr
    #     fpath = join(pharn.test_dump_dpath, 'urban_mapper_test_pred_' + suffix + '.txt')
    #     print('fpath = {!r}'.format(fpath))
    #     ub.writeto(fpath, text)
    #     print(ub.codeblock(
    #         '''
    #         # Execute on remote computer
    #         cd ~/Dropbox/TopCoder
    #         rsync aretha:{fpath} .
    #         '''
    #     ).format(fpath=fpath))

    # def one_channel_version():
    #     mode = 'pred'
    #     restitched_pred = pharn._restitch_type(mode, blend='vote')
    #     if True:
    #         pharn._restitch_type('blend_' + mode, blend=None)
    #     restitched_pred = eval_dataset.fullres.align(restitched_pred)

    #     # Convert to submission output format
    #     post_kw = dict(k=15, n_iters=1, dist_thresh=5, watershed=True)
    #     # post_kw = dict(k=0, watershed=False)
    #     post_idstr = compact_idstr(post_kw)

    #     lines = []
    #     for ix, fpath in enumerate(ub.ProgIter(restitched_pred, label='rle')):
    #         pred = imutil.imread(fpath)
    #         cc_labels = eval_dataset.task.instance_label(pred, **post_kw)

    #         fname = splitext(basename(fpath))[0]
    #         (width, height), runlen = imutil.run_length_encoding(cc_labels)

    #         lines.append(fname)
    #         lines.append('{},{}'.format(width, height))
    #         lines.append(','.join(list(map(str, runlen))))

    #     text = '\n'.join(lines)
    #     suffix = '_'.join(pharn.test_dump_dpath.split('/')[-2:]) + '_' + mode + '_' + post_idstr
    #     fpath = join(pharn.test_dump_dpath, 'urban_mapper_test_pred_' + suffix + '.txt')
    #     ub.writeto(fpath, text)

    # if '/unet2/' in train_dpath:
    #     two_channel_version()
    # else:
    #     one_channel_version()

    # Submission URL
    # https://community.topcoder.com/longcontest/
    # https://community.topcoder.com/longcontest/?module=Submit&compid=57607&rd=17007&cd=15282
    """
    Leaderboards:
        https://community.topcoder.com/longcontest/?module=ViewStandings&rd=17007
    """


def eval_internal_testset():
    """
    Working with the testing set (don't submit with this)

    CommandLine:
        python -m clab.live.urban_mapper eval_internal_testset --arch=unet2 \
            --epoch=386 \
            --train-dpath ~/remote/aretha/data/work/urban_mapper2/arch/unet2/train/input_4214-guwsobde/solver_4214-guwsobde_unet2_mmavmuou_tqynysqo_a=1,c=RGB,n_ch=5,n_cl=4

    Ignore:
        import ubelt as ub
        epoch = 100
        train_dpath = ub.truepath('~/remote/aretha/data/work/urban_mapper2/arch/unet2/train/input_4214-guwsobde/solver_4214-guwsobde_unet2_mmavmuou_tqynysqo_a=1,c=RGB,n_ch=5,n_cl=4')

    Script:
        >>> eval_internal_testset()
    """
    MODE = 'DENSE'
    MODE = 'UNET6CH'

    if MODE == 'DENSE':
        arch = 'dense_unet'
        train_dpath = ub.truepath(
            '~/remote/aretha/data/work/urban_mapper4/arch/dense_unet/train/input_25800-phpjjsqu/'
            'solver_25800-phpjjsqu_dense_unet_mmavmuou_zeosddyf_a=1,c=RGB,n_ch=6,n_cl=4')
        epoch = None
        use_aux_diff = True
        epoch = 26

    elif MODE == 'UNET6CH':
        arch = 'unet2'
        train_dpath = ub.truepath(
            '~/remote/aretha/data/work/urban_mapper2/arch/unet2/train/input_25800-hemanvft/'
            'solver_25800-hemanvft_unet2_mmavmuou_stuyuerd_a=1,c=RGB,n_ch=6,n_cl=4')
        # epoch = 15
        epoch = None
        epoch = 34
        use_aux_diff = True

        train_dpath = '/home/local/KHQ/jon.crall/data/work/urban_mapper2/arch/unet2/train/input_52200-fqljkqlk/solver_52200-fqljkqlk_unet2_ybypbjtw_smvuzfkv_a=1,c=RGB,n_ch=6,n_cl=4'
        epoch = 0
        epoch = 5
    else:
        raise KeyError(MODE)

    from clab.live.urban_train import load_task_dataset
    datasets = load_task_dataset('urban_mapper_3d', combine=False, arch=arch)
    test_dataset = datasets['test']
    test_dataset.use_aux_diff = use_aux_diff
    test_dataset.with_gt = False
    test_dataset.inputs.make_dumpsafe_names()
    test_dataset.tag = 'test'

    load_path = get_snapshot(train_dpath, epoch=epoch)
    print('load_path = {!r}'.format(load_path))

    pharn = PredictHarness(test_dataset)
    test_dataset.center_inputs = pharn.load_normalize_center(train_dpath)
    pharn.hack_dump_path(load_path)
    task = test_dataset.task

    # needs_predict = len(pharn._restitch_type('probs', blend='avew', force=0)) == 0
    paths = {}
    paths['probs'] = glob.glob(join(pharn.test_dump_dpath, 'stitched', 'probs', '*.h5'))
    paths['probs1'] = glob.glob(join(pharn.test_dump_dpath, 'stitched', 'probs1', '*.h5'))

    if len(paths['probs']) < 88:
        # gpu part
        pharn.load_snapshot(load_path)
        pharn.run()

    paths = {}
    paths['probs'] = glob.glob(join(pharn.test_dump_dpath, 'stitched', 'probs', '*.h5'))
    paths['probs1'] = glob.glob(join(pharn.test_dump_dpath, 'stitched', 'probs1', '*.h5'))
    if False:
        pharn._blend_full_probs(task, 'probs', npy_fpaths=paths['probs'])
        pharn._blend_full_probs(task, 'probs1', npy_fpaths=paths['probs1'])

    @ub.memoize
    def gt_info_from_path(pred_fpath):
        gtl_fname = ub.augpath(basename(pred_fpath), suffix='_GTL', ext='.tif')
        gti_fname = ub.augpath(basename(pred_fpath), suffix='_GTI', ext='.tif')
        dsm_fname = ub.augpath(basename(pred_fpath), suffix='_DSM', ext='.tif')
        bgr_fname = ub.augpath(basename(pred_fpath), suffix='_RGB', ext='.tif')
        gtl_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), gtl_fname)
        gti_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), gti_fname)
        dsm_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), dsm_fname)
        bgr_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), bgr_fname)

        gti = util.imread(gti_fpath)
        gtl = util.imread(gtl_fpath)
        dsm = util.imread(dsm_fpath)
        bgr = util.imread(bgr_fpath)
        uncertain = (gtl == 65)
        return gti, uncertain, dsm, bgr

    def hypersearch_probs():
        prob_paths  = paths['probs']
        prob1_paths = paths['probs1']

        # https://github.com/fmfn/BayesianOptimization
        # https://github.com/fmfn/BayesianOptimization/blob/master/examples/usage.py
        # https://github.com/fmfn/BayesianOptimization/blob/master/examples/exploitation%20vs%20exploration.ipynb
        # subx = [0, 1, 2, 3, 4, 5]
        subx = [2, 4, 5, 9, 10, 14, 17, 18, 20, 30, 33, 39, 61, 71, 72, 73, 75, 81, 84]
        from bayes_opt import BayesianOptimization

        def best(self):
            return {'max_val': self.Y.max(),
                    'max_params': dict(zip(self.keys,
                                           self.X[self.Y.argmax()]))}

        @ub.memoize
        def memo_read_arr(fpath):
            return util.read_arr(fpath)

        def seeded_objective(**params):
            seed_thresh, mask_thresh, min_seed_size, min_size = ub.take(
                params, 'seed_thresh, mask_thresh, min_seed_size, min_size'.split(', '))
            fscores = []
            sub0 = ub.take(prob_paths, subx)
            sub1 = ub.take(prob1_paths, subx)
            sub0 = prob_paths
            sub1 = prob1_paths
            for path, path1 in zip(sub0, sub1):
                gti, uncertain, dsm, bgr = gt_info_from_path(path)

                probs = memo_read_arr(path)
                seed_probs = probs[:, :, task.classname_to_id['inner_building']]
                seed = (seed_probs > seed_thresh).astype(np.uint8)

                probs1 = memo_read_arr(path1)
                mask_probs = probs1[:, :, 1]
                mask = (mask_probs > mask_thresh).astype(np.uint8)

                pred = seeded_instance_label(seed, mask,
                                             min_seed_size=min_seed_size,
                                             min_size=min_size)
                scores = instance_fscore(gti, uncertain, dsm, pred)
                fscore = scores[0]
                fscores.append(fscore)
            mean_fscore = np.mean(fscores)
            return mean_fscore
        # params = {'mask_thresh': 0.7664, 'min_seed_size': 48.5327, 'min_size': 61.8757, 'seed_thresh': 0.4090}

        seeded_bounds = {
            'mask_thresh': (.4, .9),
            'seed_thresh': (.4, .9),
            'min_seed_size': (0, 100),
            'min_size': (0, 100),
        }
        n_init = 50
        seeded_bo = BayesianOptimization(seeded_objective, seeded_bounds)
        seeded_bo.explore(pd.DataFrame([
            {'mask_thresh': 0.9000, 'min_seed_size': 100.0000, 'min_size': 100.0000, 'seed_thresh': 0.4000},
            {'mask_thresh': 0.8, 'seed_thresh': 0.5, 'min_seed_size': 20, 'min_size': 0},
            {'mask_thresh': 0.5, 'seed_thresh': 0.8, 'min_seed_size': 20, 'min_size': 0},
            {'mask_thresh': 0.8338, 'min_seed_size': 25.7651, 'min_size': 38.6179, 'seed_thresh': 0.6573},
            {'mask_thresh': 0.6225, 'min_seed_size': 93.2705, 'min_size': 5, 'seed_thresh': 0.4401},
            {'mask_thresh': 0.7870, 'min_seed_size': 85.1641, 'min_size': 64.0634, 'seed_thresh': 0.4320},
            {'mask_thresh': 0.8367, 'seed_thresh': 0.4549, 'min_seed_size': 97, 'min_size': 33},  # 'max_val': 0.8708
            {'mask_thresh': 0.8367, 'min_seed_size': 97.0000, 'min_size': 33.0000, 'seed_thresh': 0.4549},  # max_val': 0.8991
            {'mask_thresh': 0.7664, 'min_seed_size': 48.5327, 'min_size': 61.8757, 'seed_thresh': 0.4090},  # 'max_val': 0.9091}
            {'mask_thresh': 0.6666, 'min_seed_size': 81.5941, 'min_size': 13.2919, 'seed_thresh': 0.4241},  # full dataset 'max_val': 0.9142}
        ]).to_dict(orient='list'))
        seeded_bo.plog.print_header(initialization=True)
        seeded_bo.init(n_init)
        print('seeded ' + ub.repr2(best(seeded_bo), nl=0, precision=4))

        gp_params = {"alpha": 1e-5, "n_restarts_optimizer": 2}

        n_iter = n_init // 2
        for kappa in [10, 5, 1]:
            seeded_bo.maximize(n_iter=n_iter, acq='ucb', kappa=kappa, **gp_params)

        print('seeded ' + ub.repr2(best(seeded_bo), nl=0, precision=4))
        print(arch)

    def draw_failures():
        prob_paths  = paths['probs']
        prob1_paths = paths['probs1']

        params = {
            'mask_thresh': 0.8338, 'min_seed_size': 25.7651,
            'min_size': 38.6179, 'seed_thresh': 0.6573
        }

        seed_thresh, mask_thresh, min_seed_size, min_size = ub.take(
            params, 'seed_thresh, mask_thresh, min_seed_size, min_size'.split(', '))
        for ix, (path, path1) in enumerate(ub.ProgIter(list(zip(prob_paths, prob1_paths)))):
            gti, uncertain, dsm, bgr = gt_info_from_path(path)

            probs = util.read_arr(path)
            seed_probs = probs[:, :, task.classname_to_id['inner_building']]
            seed = (seed_probs > seed_thresh).astype(np.uint8)

            probs1 = util.read_arr(path1)
            mask_probs = probs1[:, :, 1]
            mask = (mask_probs > mask_thresh).astype(np.uint8)

            pred = seeded_instance_label(seed, mask,
                                         min_seed_size=min_seed_size,
                                         min_size=min_size)

            scores, infod = instance_fscore(gti, uncertain, dsm, pred, info=True)

            fn_labels = infod['fn']

            # visualize failure cases
            from clab.torch.metrics import CumMovingAve
            ave_scores = CumMovingAve()
            if True:
                from clab.tasks import urban_mapper_3d
                from clab.tasks.urban_mapper_3d import instance_contours, draw_contours

                gtl = (uncertain * 65)
                # tp_assign = infod['tp']
                fp_labels = infod['fp']
                fn_labels = infod['fn']

                fn_contours = list(ub.flatten(ub.take(instance_contours(gti), fn_labels)))
                fp_contours = list(ub.flatten(ub.take(instance_contours(pred), fp_labels)))

                color_probs = util.make_heatmask(mask_probs)
                color_probs[:, :, 3] *= .3
                blend_probs = util.overlay_colorized(color_probs, bgr, keepcolors=False)

                # Draw False Positives and False Negatives with a big thickness
                DEEP_SKY_BLUE_BGR = (255, 191, 0)
                MAGENTA_BGR = (255, 0, 255)
                RED_BGR = (0, 0, 255)
                GREEN_BGR = (0, 255, 0)

                draw_img = blend_probs
                draw_img = draw_contours(draw_img, fp_contours, thickness=6, alpha=.5, color=MAGENTA_BGR)
                draw_img = draw_contours(draw_img, fn_contours, thickness=6, alpha=.5, color=RED_BGR)

                # Overlay GT and Pred contours
                draw_img = urban_mapper_3d.draw_instance_contours(
                    draw_img, gti, gtl=gtl, color=GREEN_BGR, thickness=2, alpha=.5)

                draw_img = urban_mapper_3d.draw_instance_contours(
                    draw_img, pred, color=DEEP_SKY_BLUE_BGR, thickness=2, alpha=.5)

                ave_scores.update(dict(zip(['fscore', 'precision', 'recall'], scores)))

                text = ub.codeblock(
                    '''
                    F-score:   {:.4f}
                    Precision: {:.4f}
                    Recall:    {:.4f}
                    '''
                ).format(*scores)

                draw_img = imutil.putMultiLineText(draw_img, text, org=(10, 70),
                                                   fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                                                   fontScale=1.5,
                                                   color=GREEN_BGR, thickness=3,
                                                   lineType=cv2.LINE_AA)

                out_fpath = ub.augpath(path.replace('/probs/', '/failures/'), ext='.png')
                from os.path import dirname
                ub.ensuredir(dirname(out_fpath))
                imutil.imwrite(out_fpath, draw_img)
                print(ave_scores.average())

        print(ave_scores.average())
        # mean_fscore = np.mean(fscores)
        # print('mean_fscore = {!r}'.format(mean_fscore))

    # draw_failures()
    hypersearch_probs()

    # Recombined predictions on chips into predictions on the original inputs
    paths = {}
    for mode in ['pred', 'pred1']:
        restitched_paths = pharn._restitch_type(mode, blend='vote')
        if 1:
            pharn._restitch_type('blend_' + mode, blend=None)
        paths[mode] = restitched_paths

    import pandas as pd
    task = test_dataset.task

    restitched_pred0 = pharn._restitch_type('pred', blend='vote')
    restitched_pred1 = pharn._restitch_type('pred1', blend='vote')

    out_fpaths = unet2_instance_restitch(restitched_pred0, restitched_pred1, task)
    test_instance_restitch(out_fpaths, task)

    # Evaluate the binary predictions by themselves
    mode = 'pred1'
    restitched_paths = paths[mode]
    scores1 = []
    for pred_fpath in ub.ProgIter(restitched_paths, label='scoring 1'):
        gti, uncertain, dsm, bgr = gt_info_from_path(pred_fpath)
        pred_seg = util.imread(pred_fpath)
        pred = task.instance_label(pred_seg, dist_thresh=5, k=12, watershed=True)
        scores1.append(instance_fscore(gti, uncertain, dsm, pred))

    scores_df1 = pd.DataFrame(scores1, columns=['fscore', 'precision', 'recall'])
    print('binary fscore {}'.format(scores_df1['fscore'].mean()))

    # ----------------------------------------
    # Combine the binary and inner predictions.

    mode = 'pred'
    restitched_paths = paths[mode]
    scores0 = []
    for pred_fpath in ub.ProgIter(restitched_paths, label='scoring seeds'):
        gti, uncertain, dsm, bgr = gt_info_from_path(pred_fpath)

        pred_seg0 = util.imread(pred_fpath)
        pred_seg1 = util.imread(pred_fpath.replace('/pred/', '/pred1/'))

        seed = (pred_seg0 == task.classname_to_id['inner_building']).astype(np.uint8)
        mask = (pred_seg1 == 1)
        pred = seeded_instance_label(seed, mask, min_seed_size=50)

        scores0.append(instance_fscore(gti, uncertain, dsm, pred))

    scores_df0 = pd.DataFrame(scores0, columns=['fscore', 'precision', 'recall'])
    print('binary scores\n{}'.format(scores_df0.mean(axis=0)))

    # -------- OLD ---------
    # hack
    if 0:
        for mode in ['blend_pred', 'blend_pred_crf']:
            restitched_paths = pharn._restitch_type(mode, blend=None)

        paths = {}
        for mode in ['pred', 'pred_crf']:
            restitched_paths = pharn._restitch_type(mode, blend='vote')
            for big_pred_fpath in ub.ProgIter(restitched_paths, label='open ' + mode):
                big_pred = imutil.imread(big_pred_fpath)

                k = 7
                n_iters = 1
                new_fpath = big_pred_fpath.replace('/' + mode + '/', '/' + mode + '_open{}x{}/'.format(k, n_iters))
                new_blend_fpath = big_pred_fpath.replace('/' + mode + '/', '/blend_' + mode + '_open{}x{}/'.format(k, n_iters))
                ub.ensuredir(os.path.dirname(new_fpath))
                ub.ensuredir(os.path.dirname(new_blend_fpath))

                pred2 = (test_dataset.task.instance_label(big_pred, k=k,
                                                          n_iters=n_iters,
                                                          watershed=False) > 0
                         ).astype(np.int8)
                imutil.imwrite(new_fpath, pred2)

                big_im_fname = basename(big_pred_fpath).replace('.png', '_RGB.tif')
                big_orig_fpath = join('/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/', big_im_fname)
                big_orig = imutil.imread(big_orig_fpath)

                big_blend_instance_pred = test_dataset.task.colorize(pred2, big_orig)
                imutil.imwrite(new_blend_fpath, big_blend_instance_pred)

        mode = 'pred_crf'
        mode = 'pred'
        restitched_paths = pharn._restitch_type(mode, blend='vote')

        big_pred_fpath = restitched_paths[17]
        orig_fname = basename(big_pred_fpath).replace('.png', '_RGB.tif')
        big_orig_fpath = join('/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/', orig_fname)
        # big_orig_fpath = '/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/TAM_Tile_017_RGB.tif'

        big_pred = imutil.imread(big_pred_fpath)
        big_orig = imutil.imread(big_orig_fpath)

        k = 3
        kernel = np.ones((k, k), np.uint8)
        import cv2
        opening = cv2.morphologyEx(big_pred, cv2.MORPH_OPEN, kernel, iterations=2)
        n_ccs, cc_labels = cv2.connectedComponents(opening.astype(np.uint8), connectivity=4)

        # cc_labels = task.instance_label(big_pred)

        big_blend_instance_pred = test_dataset.task.instance_colorize(cc_labels, big_orig)
        # big_blend_instance_pred = task.colorize(cc_labels > 0, big_orig)
        restitched_pred_dpath = ub.ensuredir((pharn.test_dump_dpath, 'restiched', 'blend_instance_' + mode))
        fname = basename(big_pred_fpath)
        imutil.imwrite(join(restitched_pred_dpath, fname), big_blend_instance_pred)

    if 1:
        import pandas as pd  # NOQA
        from clab.metrics import confusion_matrix, jaccard_score_from_confusion  # NOQA
        from clab.torch import filters  # NOQA

        paths = {}
        for mode in ['pred', 'pred_crf']:
            restitched_paths = pharn._restitch_type(mode, blend='vote')
            paths[mode] = restitched_paths

        scores = {}
        import cv2
        for mode in ['pred', 'pred_crf']:
            print('mode = {!r}'.format(mode))
            restitched_paths = paths[mode]

            for n_iters in range(1, 2):
                for k in range(5, 10, 2):
                    for watershed in [False, True]:
                        cfsn2 = np.zeros((3, 3))
                        for big_pred_fpath in restitched_paths:
                            big_pred = imutil.imread(big_pred_fpath)

                            big_gt_fname = basename(big_pred_fpath).replace('.png', '_GTL.tif')
                            big_gt_fpath = join('/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/', big_gt_fname)
                            big_gt = imutil.imread(big_gt_fpath)
                            big_gt[big_gt == 2] = 0
                            big_gt[big_gt == 6] = 1
                            big_gt[big_gt == 65] = 2

                            pred2 = (test_dataset.task.instance_label(
                                big_pred, k=k, n_iters=n_iters,
                                watershed=watershed) > 0).astype(np.int8)

                            # # cfsn1 += confusion_matrix(big_gt.ravel(), big_pred.ravel(), labels=[0, 1, 2])
                            # if k > 1:
                            #     kernel = np.ones((k, k), np.uint8)
                            #     opening = cv2.morphologyEx(big_pred, cv2.MORPH_OPEN, kernel, iterations=n_iters)
                            #     # opening = filters.watershed_filter(opening)
                            #     # n_ccs, cc_labels = cv2.connectedComponents(opening.astype(np.uint8), connectivity=4)
                            #     # pred2 = (cc_labels > 0).astype(np.int)
                            #     pred2 = opening
                            # else:
                            #     pred2 = big_pred

                            cfsn2 += confusion_matrix(big_gt.ravel(), pred2.ravel(), labels=[0, 1, 2])

                        miou = jaccard_score_from_confusion(cfsn2)[0:2].mean()
                        scores[(mode, k, n_iters, watershed)] = miou
                        print('mode={}, k={:3d}, n_iters={}, w={} miou = {!r}'.format(mode, k, n_iters, int(watershed), miou))

        print(pd.Series(scores).sort_values())


class PredictHarness(object):
    def __init__(pharn, dataset):
        pharn.dataset = dataset
        pharn.xpu = xpu_device.XPU.from_argv()
        pharn.model = None
        pharn.test_dump_dpath = None

    def load_normalize_center(pharn, train_dpath):
        info_dpath = join(train_dpath, 'train_info.json')
        info = util.read_json(info_dpath)
        # TODO: better deserialization
        from clab.torch import transforms
        transform_list = []
        for tup in info['hack_centers']:
            classname = tup[0]
            state = tup[1]
            cls = getattr(transforms, classname, None)
            transform_list.append(cls(**state))
        centering = transforms.ZipTransforms(transform_list)
        return centering

    def load_snapshot(pharn, load_path):
        print('Loading snapshot onto {}'.format(pharn.xpu))
        snapshot = torch.load(load_path, map_location=pharn.xpu.map_location())

        if 'model_kw' not in snapshot:
            # FIXME: we should be able to get information from the snapshot
            print('warning snapshot not saved with modelkw')
            n_classes = pharn.dataset.n_classes
            n_channels = pharn.dataset.n_channels

        # Infer which model this belongs to
        # FIXME: The model must be constructed with the EXACT same kwargs This
        # will be easier when onnx supports model serialization.
        if snapshot['model_class_name'] == 'UNet':
            pharn.model = models.UNet(in_channels=n_channels,
                                      n_classes=n_classes,
                                      nonlinearity='leaky_relu')
        elif snapshot['model_class_name'] == 'SegNet':
            pharn.model = models.SegNet(in_channels=n_channels, n_classes=n_classes)
        elif snapshot['model_class_name'] == 'UNet2':
            from clab.live import unet2
            pharn.model = unet2.UNet2(
                in_channels=n_channels, n_classes=n_classes, n_alt_classes=3,
                nonlinearity='leaky_relu'
            )
        elif snapshot['model_class_name'] == 'DenseUNet':
            from clab.live import unet3
            pharn.model = unet3.DenseUNet(
                in_channels=n_channels, n_classes=n_classes, n_alt_classes=3,
            )
        else:
            raise NotImplementedError(snapshot['model_class_name'])

        pharn.model = pharn.xpu.to_xpu(pharn.model)
        pharn.model.load_state_dict(snapshot['model_state_dict'])

    def hack_dump_path(pharn, load_path):
        # HACK
        eval_dpath = ub.ensuredir((pharn.dataset.task.workdir, pharn.dataset.tag, 'input_' + pharn.dataset.input_id))
        subdir = list(ub.take(os.path.splitext(load_path)[0].split('/'), [-3, -1]))
        # base output dump path on the training id string
        pharn.test_dump_dpath = ub.ensuredir((eval_dpath, '/'.join(subdir)))
        print('pharn.test_dump_dpath = {!r}'.format(pharn.test_dump_dpath))

    def _restitch_type(pharn, mode, blend='vote', force=True):
        """
        hacky code to restitch parts into a whole segmentation based on chip filenames

        mode = 'probs'
        blend = 'avew'
        force = 1
        """
        if mode.startswith('probs'):
            part_paths = sorted(glob.glob(pharn.test_dump_dpath + '/{}/*.npy'.format(mode)))
        else:
            part_paths = sorted(glob.glob(pharn.test_dump_dpath + '/{}/*.png'.format(mode)))

        output_dpath = ub.ensuredir((pharn.test_dump_dpath, 'restiched', mode))
        if not force:
            restitched_paths = sorted(glob.glob(output_dpath + '/*.npy'.format(mode)))
            if len(restitched_paths) > 0:
                return restitched_paths
        restitched_paths = pharn.dataset.task.restitch(output_dpath, part_paths,
                                                       blend=blend)
        return restitched_paths

    def _blend_full_probs(pharn, task, mode='probs1', npy_fpaths=None):
        """
        Ignore:
            mode = 'probs1'
            pharn._restitch_type('probs1', blend='avew')

            from clab.profiler import profile_onthefly
            profile_onthefly(pharn._blend_full_probs)(task, mode='probs', npy_fpaths=npy_fpaths)
            profile_onthefly(foo)(npy_fpaths)
        """
        if npy_fpaths is None:
            dpath = join(pharn.test_dump_dpath, 'restiched', mode)
            npy_fpaths = glob.glob(join(dpath, '*.npy'))

        out_dpath = ub.ensuredir((pharn.test_dump_dpath, 'restiched', 'blend_' + mode))

        for fpath in ub.ProgIter(npy_fpaths, label='viz full probs'):

            out_fpath = join(out_dpath, basename(fpath))
            gtl_fname = basename(out_fpath).replace('.npy', '_GTL.tif')
            gti_fname = basename(out_fpath).replace('.npy', '_GTI.tif')
            bgr_fname = basename(out_fpath).replace('.npy', '_RGB.tif')
            gtl_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), gtl_fname)
            gti_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), gti_fname)
            bgr_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), bgr_fname)

            gtl = util.imread(gtl_fpath)
            gti = util.imread(gti_fpath)
            bgr = util.imread(bgr_fpath)
            probs = util.read_arr(fpath)

            # Dump each channel
            from clab.tasks import urban_mapper_3d
            # from clab import profiler
            # _ = profiler.profile_onthefly(urban_mapper_3d.draw_instance_contours)(blend_probs, gti, gtl)

            for c in reversed(range(probs.shape[2])):
                if mode.endswith('1'):
                    # hack
                    name = ['non-building', 'building', 'uncertain'][c]
                else:
                    name = task.classnames[c]

                if name in task.ignore_classnames:
                    continue
                c_dpath = ub.ensuredir(join(out_dpath, 'c{}_{}'.format(c, name)))
                c_fname = ub.augpath(basename(fpath), ext='.png')
                c_fpath = join(c_dpath, c_fname)

                color_probs = util.make_heatmask(probs[:, :, c])[:, :, 0:3]
                blend_probs = util.overlay_colorized(color_probs, bgr, alpha=.3)

                draw_img = urban_mapper_3d.draw_instance_contours(
                    blend_probs, gti, gtl, thickness=2, alpha=.4)

                util.imwrite(c_fpath, draw_img)

    def color_probs(pharn, task):
        """
        Ignore:
            pharn._restitch_type('blend_probs/c0_non-building', blend=None)
            pharn._restitch_type('blend_probs/c1_inner-building', blend=None)
            pharn._restitch_type('blend_probs/c2_outer-building', blend=None)

            pharn._restitch_type('blend_probs1/c0_non-building', blend=None)
            pharn._restitch_type('blend_probs1/c1_building', blend=None)
        """

        mode = 'probs1'
        mode = 'probs'

        dpath = join(pharn.test_dump_dpath, mode)

        out_dpath = join(pharn.test_dump_dpath, 'blend_' + mode)

        npy_fpaths = glob.glob(join(dpath, '*.npy'))

        bgr_paths = pharn.dataset.inputs.paths['im']
        gtl_paths = pharn.dataset.inputs.paths['gt']
        npy_fpaths = pharn.dataset.inputs.align(npy_fpaths)

        for ix, fpath in enumerate(ub.ProgIter(npy_fpaths)):
            gt = util.imread(gtl_paths[ix])
            bgr = util.imread(bgr_paths[ix])

            probs = util.read_arr(fpath)

            # Dump each channel
            for c in reversed(range(probs.shape[0])):
                if mode.endswith('1'):
                    # hack
                    name = ['non-building', 'building', 'uncertain'][c]
                else:
                    name = task.classnames[c]
                if name in task.ignore_classnames:
                    continue
                c_dpath = ub.ensuredir(join(out_dpath, 'c{}_{}'.format(c, name)))
                c_fname = ub.augpath(basename(fpath), ext='.png')
                c_fpath = join(c_dpath, c_fname)

                color_probs = util.make_heatmask(probs[:, :, c])[:, :, 0:3]
                blend_probs = util.overlay_colorized(color_probs, bgr, alpha=.3)

                draw_img = draw_gt_contours2(blend_probs, gt, thickness=2, alpha=.5)
                util.imwrite(c_fpath, draw_img)
        pharn._restitch_type('blend_probs1/c0_non-building', blend='avew')
        pharn._restitch_type('blend_probs1/c1_building', blend='avew')

    # from clab.profiler import profile_onthefly
    # @profile_onthefly
    def run(pharn):
        print('Preparing to predict {} on {}'.format(pharn.model.__class__.__name__, pharn.xpu))
        pharn.model.train(False)

        # Hack in the restitching here to not have to deal with expensive IO
        def _extract_part_grid(paths):
            # hack to use filenames to extract upper left locations of tiles in
            # the larger image.
            rc_locs = [[int(x) for x in basename(p).split('.')[0].split('_')[-2:]]
                       for p in paths]
            return rc_locs

        def stitch_tiles_avew(rc_locs, tiles):
            """
            Recombine parts back into an entire image

            Example:
                >>> rc_locs = [(0, 0), (0, 5), (0, 10)]
                >>> tiles = [np.ones((1, 7, 3)) + i for i in range(len(rc_locs))]
                >>> tiles = [np.ones((1, 7)) + i for i in range(len(rc_locs))]
            """
            shapes = [t.shape[0:2] for t in tiles]
            n_channels = 1 if len(tiles[0].shape) == 2 else tiles[0].shape[2]
            bboxes = np.array([
                (r, c, r + h, c + w)
                for ((r, c), (h, w)) in zip(rc_locs, shapes)
            ])
            stiched_wh = tuple(bboxes.T[2:4].max(axis=1))
            stiched_shape = stiched_wh
            if n_channels > 1:
                stiched_shape = stiched_wh + (n_channels,)
            sums = np.zeros(stiched_shape)
            nums = np.zeros(stiched_wh)

            # assume all shapes are the same
            h, w = shapes[0]
            weight = np.ones((h, w) )
            # Weight borders less than center
            # should really use receptive fields for this calculation
            # but this should be fine.
            weight[:h // 4]  = .25
            weight[-h // 4:] = .25
            weight[:w // 4]  = .25
            weight[-w // 4:] = .25
            weight3c = weight
            if n_channels > 1:
                weight3c = weight[:, :, None]

            # Assume we are not in log-space here, so the weighted average
            # formula does not need any exponentiation.
            for bbox, tile in zip(bboxes, tiles):
                r1, c1, r2, c2 = bbox
                sums[r1:r2, c1:c2] += (tile * weight3c)
                nums[r1:r2, c1:c2] += weight

            if len(sums.shape) == 2:
                stiched = sums / nums
            else:
                stiched = sums / nums[:, :, None]
            return stiched

        groupids = [basename(p).split('_part')[0]
                    for p in pharn.dataset.inputs.dump_im_names]
        grouped_indices = ub.group_items(range(len(groupids)), groupids)

        # map(len, grouped_indices)
        # ub.chunks
        #     loader = torch.utils.data.DataLoader(
        #         pharn.dataset, shuffle=False,
        #         pin_memory=True,
        #         num_workers=0,
        #         batch_size=1,
        #     )

        output_dpath = join(pharn.test_dump_dpath, 'stitched')
        ub.ensuredir(output_dpath)

        # prog = ub.ProgIter(length=len(grouped_indices), label='predict group proba', verbose=3)

        import tqdm
        for key, groupxs in tqdm.tqdm(grouped_indices.items(), desc='predict group proba'):

            grouped_probs = ub.odict()
            grouped_probs[''] = []
            grouped_probs['1'] = []

            for ix in tqdm.tqdm(groupxs, desc='pred'):

                if pharn.dataset.with_gt:
                    inputs_ = pharn.dataset[ix][0]
                else:
                    inputs_ = pharn.dataset[ix]
                inputs_ = inputs_[None, ...]

                if not isinstance(inputs_, (list, tuple)):
                    inputs_ = [inputs_]

                inputs_ = pharn.xpu.to_xpu_var(*inputs_)
                outputs = pharn.model.forward(inputs_)

                for ox in range(len(outputs)):
                    suffix = '' if ox == 0 else str(ox)

                    output_tensor = outputs[ox]
                    log_prob_tensor = torch.nn.functional.log_softmax(output_tensor, dim=1)[0]
                    prob_tensor = torch.exp(log_prob_tensor)
                    probs = np.ascontiguousarray(prob_tensor.data.cpu().numpy().transpose(1, 2, 0))

                    grouped_probs[suffix].append(probs)

            rc_locs = _extract_part_grid(ub.take(pharn.dataset.inputs.dump_im_names, groupxs))
            for suffix, tiles in grouped_probs.items():
                # from clab.profiler import profile_onthefly
                # profile_onthefly(stitch_tiles_ave)(rc_locs, tiles, weighted=True)
                stitched = stitch_tiles_avew(rc_locs, tiles)

                dpath = ub.ensuredir(join(output_dpath, 'probs' + suffix))
                fpath = join(dpath, key + '.h5')
                util.write_h5arr(fpath, stitched)

        # if False:
        #     loader = torch.utils.data.DataLoader(
        #         pharn.dataset, shuffle=False,
        #         pin_memory=True,
        #         num_workers=0,
        #         batch_size=1,
        #     )
        #     prog = ub.ProgIter(length=len(loader), label='predict proba')
        #     for ix, loaded in enumerate(prog(loader)):
        #         fname = pharn.dataset.inputs.dump_im_names[ix]
        #         fname = os.path.splitext(fname)[0] + '.png'

        #         if pharn.dataset.with_gt:
        #             inputs_ = loaded[0]
        #         else:
        #             inputs_ = loaded

        #         if not isinstance(inputs_, (list, tuple)):
        #             inputs_ = [inputs_]

        #         inputs_ = pharn.xpu.to_xpu_var(*inputs_)
        #         outputs = pharn.model.forward(inputs_)

        #         if not isinstance(outputs, (list, tuple)):
        #             outputs = [outputs]

        #         for ox in range(len(outputs)):
        #             suffix = '' if ox == 0 else str(ox)

        #             output_tensor = outputs[ox]
        #             log_prob_tensor = torch.nn.functional.log_softmax(output_tensor, dim=1)[0]
        #             prob_tensor = torch.exp(log_prob_tensor)
        #             probs = prob_tensor.data.cpu().numpy().transpose(1, 2, 0)

        #             output_dict = {
        #                 'probs' + suffix: probs,
        #             }

        #             for key, data in output_dict.items():
        #                 dpath = join(pharn.test_dump_dpath, key)
        #                 ub.ensuredir(dpath)
        #                 fpath = join(dpath, fname)
        #                 if key == 'probs' + suffix:
        #                     fpath = ub.augpath(fpath, ext='.h5')
        #                     # fpath = ub.augpath(fpath, ext='.npy')
        #                     util.write_arr(fpath, data)
        #                     # util.write_arr(fpath, data)
        #                 else:
        #                     imutil.imwrite(fpath, data)


# def erode_ccs(ccs):
#     pass


def draw_gt_contours2(img, gt, thickness=4, alpha=1):
    import cv2

    border = cv2.copyMakeBorder(gt, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0 )
    _, contours, hierarchy = cv2.findContours(border, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE, offset=(-1, -1))

    BGR_GREEN = (0, 255, 0)
    img = util.ensure_float01(img)
    base = np.ascontiguousarray((255 * img[:, :, 0:3]).astype(np.uint8))
    if alpha >= 1:
        draw_img = cv2.drawContours(
            image=base, contours=contours, contourIdx=-1, color=BGR_GREEN,
            thickness=thickness)
    else:
        # Draw an image to overlay first
        draw_img = cv2.drawContours(
            image=np.zeros(base.shape, dtype=np.uint8), contours=contours,
            contourIdx=-1, color=BGR_GREEN, thickness=thickness)
        contour_overlay = util.ensure_alpha_channel(draw_img, alpha=0)
        contour_overlay.T[3].T[draw_img.sum(axis=2) > 0] = alpha

        # zero out the edges to avoid visualization errors
        contour_overlay[0:thickness, :, :] = 0
        contour_overlay[-thickness:, :, :] = 0
        contour_overlay[:, 0:thickness, :] = 0
        contour_overlay[:, -thickness:, :] = 0

        draw_img = util.overlay_alpha_images(contour_overlay, base)
        draw_img = np.ascontiguousarray((255 * draw_img[:, :, 0:3]).astype(np.uint8))
    return draw_img


def draw_gt_contours(img, gti, thickness=4):
    import cv2

    rc_locs = np.where(gti > 0)
    grouped_cc_xys = util.group_items(
        np.ascontiguousarray(np.vstack(rc_locs[::-1]).T),
        gti[rc_locs], axis=0
    )
    gt_hulls = ub.map_vals(cv2.convexHull, grouped_cc_xys)
    BGR_GREEN = (0, 255, 0)
    img = util.ensure_float01(img)
    draw_img = np.ascontiguousarray((255 * img[:, :, 0:3]).astype(np.uint8))
    draw_img = cv2.drawContours(
        image=draw_img, contours=list(gt_hulls.values()), contourIdx=-1,
        color=BGR_GREEN, thickness=thickness)
    return draw_img


def draw_with_gt(task, pred, gti, bgr):
    blend_pred = task.instance_colorize(pred, bgr)
    draw_img = draw_gt_contours(blend_pred, gti)
    return draw_img


def unet2_instance_restitch(restitched_pred0, restitched_pred1, task):
    from os.path import dirname
    out_fpaths = []
    # restitched_pred0 = eval_dataset.fullres.align(restitched_pred1)
    for pred1_fpath in ub.ProgIter(restitched_pred1):
        # CUSTOM INSTANCE RESTITCHING
        pred_seg0 = util.imread(pred1_fpath.replace('/pred1/', '/pred/'))
        pred_seg1 = util.imread(pred1_fpath)

        seed = (pred_seg0 == task.classname_to_id['inner_building']).astype(np.uint8)
        mask = (pred_seg1 == 1)
        pred = seeded_instance_label(seed, mask, min_seed_size=75)
        out_fpath = pred1_fpath.replace('/pred1/', '/instance_pred/')

        ub.ensuredir(dirname(out_fpath))
        util.imwrite(out_fpath, (pred > 0).astype(np.uint8))
        out_fpaths.append(out_fpath)
    return out_fpaths


def test_instance_restitch(out_fpaths, task):
    from os.path import dirname, exists
    import cv2
    all_scores = []
    for out_fpath in ub.ProgIter(out_fpaths, freq=1, adjust=False):
        gtl_fname = basename(out_fpath).replace('.png', '_GTL.tif')
        gti_fname = basename(out_fpath).replace('.png', '_GTI.tif')
        dsm_fname = basename(out_fpath).replace('.png', '_DSM.tif')
        bgr_fname = basename(out_fpath).replace('.png', '_RGB.tif')
        gtl_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), gtl_fname)
        gti_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), gti_fname)
        dsm_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), dsm_fname)
        bgr_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), bgr_fname)

        blend_fpath = out_fpath.replace('/instance_pred', '/blend_instance_pred')
        ub.ensuredir(dirname(blend_fpath))

        if exists(gti_fpath):
            bgr = util.imread(bgr_fpath)

            pred = util.imread(out_fpath)

            pred_ccs = cv2.connectedComponents(pred, connectivity=4)[1]
            blend_pred = task.instance_colorize(pred_ccs, bgr)
            gti = util.imread(gti_fpath)
            gtl = util.imread(gtl_fpath)
            dsm = util.imread(dsm_fpath)
            uncertain = (gtl == 65)

            scores, assign = instance_fscore(gti, uncertain, dsm, pred_ccs, info=True)
            all_scores.append(scores)

            blend_pred = draw_gt_contours(blend_pred, gti)
            util.imwrite(blend_fpath, blend_pred)
    return out_fpaths


def cc_locs(mask):
    import cv2
    ccs = cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)[1]
    rc_locs = np.where(mask > 0)
    rc_ids = ccs[rc_locs]
    rc_arrs = np.ascontiguousarray(np.vstack(rc_locs).T)
    cc_to_loc = util.group_items(rc_arrs, rc_ids, axis=0)
    return cc_to_loc


def mask_instance_label(pred, k=15, n_iters=1, dist_thresh=5,
                        min_size=0, watershed=False):
    import cv2
    mask = pred
    # noise removal
    if k > 1:
        kernel = np.ones((k, k), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel,
                                iterations=n_iters)

    if watershed:
        from clab.torch import filters
        mask = filters.watershed_filter(mask, dist_thresh=dist_thresh)

    mask = mask.astype(np.uint8)
    n_ccs, pred_ccs = cv2.connectedComponents(mask, connectivity=4)

    if min_size > 0:
        # Remove small predictions
        for inner_id, inner_rcs in cc_locs(pred_ccs).items():
            if len(inner_rcs) < min_size:
                pred_ccs[tuple(inner_rcs.T)] = 0

    return pred_ccs


def seeded_instance_label(seed, mask, inner_k=0, outer_k=0, post_k=0,
                          min_seed_size=0, min_size=0):
    import cv2

    mask = mask.astype(np.uint8)
    seed = seed.astype(np.uint8)

    if inner_k > 0:
        kernel = np.ones((inner_k, inner_k), np.uint8)
        seed = cv2.morphologyEx(seed, cv2.MORPH_OPEN, kernel,
                                 iterations=1)

    if min_seed_size > 0:
        # Remove very small seeds
        for inner_id, inner_rcs in cc_locs(seed).items():
            if len(inner_rcs) < min_seed_size:
                seed[tuple(inner_rcs.T)] = 0

    seed_ccs = cv2.connectedComponents(seed, connectivity=4)[1]

    # Remove seeds not surrounded by a mask
    seed[(seed & ~mask)] = 0

    if outer_k > 1:
        mask = cv2.morphologyEx(mask, cv2.MORPH_ERODE,
                                np.ones((outer_k, outer_k), np.uint8),
                                iterations=1)
        # Ensure we dont clobber a seed
        mask[seed.astype(np.bool)] = 1

    dmask1 = cv2.dilate(mask, np.ones((3, 3)))
    dmask2 = cv2.dilate(dmask1, np.ones((3, 3)))

    # Build a topological wall between mask components
    twall = dmask1 - mask

    # Pixels beyond the wall region are sure background
    sure_bg = 1 - dmask2

    # prepare watershed seeds
    # Label sure background as 1
    wseed = sure_bg.astype(np.int)
    # Add the seeds starting at 2
    seed_mask = seed_ccs > 0
    seed_labels = seed_ccs[seed_mask]
    wseed[seed_mask] = seed_labels + 1
    # The unsure region is now labeled as zero

    topology = np.dstack([twall * 255] * 3)
    markers = np.ascontiguousarray(wseed.astype(np.int32).copy())
    markers = cv2.watershed(topology, markers)
    # Remove background and border labels
    markers[markers <= 1] = 0

    instance_mask = (markers > 0).astype(np.uint8)

    if post_k > 0:
        mask = cv2.morphologyEx(mask, cv2.MORPH_ERODE,
                                np.ones((post_k, post_k), np.uint8),
                                iterations=1)

    pred_ccs = cv2.connectedComponents(instance_mask, connectivity=4)[1]

    if min_size > 0:
        # Remove small predictions
        for inner_id, inner_rcs in cc_locs(pred_ccs).items():
            if len(inner_rcs) < min_size:
                pred_ccs[tuple(inner_rcs.T)] = 0
    return pred_ccs


def instance_fscore(gti, uncertain, dsm, pred, info=False):
    """
    path = '/home/local/KHQ/jon.crall/data/work/urban_mapper/eval/input_4224-rwyxarza/solver_4214-yxalqwdk_unet_vgg_nttxoagf_a=1,n_ch=5,n_cl=3/_epoch_00000236/restiched/pred'

    path = ub.truepath(
        '~/remote/aretha/data/work/urban_mapper2/test/input_4224-exkudlzu/'
        'solver_4214-guwsobde_unet_mmavmuou_eqnoygqy_a=1,c=RGB,n_ch=5,n_cl=4/'
        '_epoch_00000154/restiched/pred')
    mode_paths = sorted(glob.glob(path + '/*.png'))

    def instance_label(pred, k=15, n_iters=1, dist_thresh=5, watershed=False):
        mask = pred

        # noise removal
        if k > 1 and n_iters > 0:
            kernel = np.ones((k, k), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel,
                                    iterations=n_iters)

        if watershed:
            from clab.torch import filters
            mask = filters.watershed_filter(mask, dist_thresh=dist_thresh)

        mask = mask.astype(np.uint8)
        n_ccs, cc_labels = cv2.connectedComponents(mask, connectivity=4)
        return cc_labels

    from clab.tasks.urban_mapper_3d import UrbanMapper3D
    task = UrbanMapper3D('', '')

    fscores = []
    for pred_fpath in ub.ProgIter(mode_paths):
        pass
        gtl_fname = basename(pred_fpath).replace('.png', '_GTL.tif')
        gti_fname = basename(pred_fpath).replace('.png', '_GTI.tif')
        dsm_fname = basename(pred_fpath).replace('.png', '_DSM.tif')
        bgr_fname = basename(pred_fpath).replace('.png', '_RGB.tif')
        gtl_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), gtl_fname)
        gti_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), gti_fname)
        dsm_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), dsm_fname)
        bgr_fpath = join(ub.truepath('~/remote/aretha/data/UrbanMapper3D/training/'), bgr_fname)

        pred_seg = util.imread(pred_fpath)

        pred = instance_label2(pred_seg, dist_thresh=d, k=k, watershed=True)
        gti = util.imread(gti_fpath)
        gtl = util.imread(gtl_fpath)
        dsm = util.imread(dsm_fpath)
        bgr = util.imread(bgr_fpath)

        uncertain = (gtl == 65)

        fscore = instance_fscore(gti, uncertain, dsm, pred)
        fscores.append(fscore)
    print('k = {!r}'.format(k))
    print('d = {!r}'.format(d))
    print(np.mean(fscores))


    from clab import profiler
    instance_fscore_ = dynamic_profile(instance_fscore)
    fscore = instance_fscore_(gti, uncertain, dsm, pred)
    instance_fscore_.profile.profile.print_stats()
    """
    def _bbox(arr):
        # r1, c1, r2, c2
        return np.hstack([arr.min(axis=0), arr.max(axis=0)])

    def cc_locs(ccs):
        rc_locs = np.where(ccs > 0)
        rc_ids = ccs[rc_locs]
        rc_arr = np.ascontiguousarray(np.vstack(rc_locs).T)
        unique_labels, groupxs = util.group_indices(rc_ids)
        grouped_arrs = util.apply_grouping(rc_arr, groupxs, axis=0)
        id_to_rc = ub.odict(zip(unique_labels, grouped_arrs))
        return id_to_rc, unique_labels, groupxs, rc_arr

    (true_rcs_arr, group_true_labels,
     true_groupxs, true_rc_arr) = cc_locs(gti)

    (pred_rcs_arr, group_pred_labels,
     pred_groupxs, pred_rc_arr) = cc_locs(pred)

    DSM_NAN = -32767
    MIN_SIZE = 100
    MIN_IOU = 0.45
    # H, W = pred.shape[0:2]

    # --- Find uncertain truth ---
    # any gt-building explicitly labeled in the GTL is uncertain
    uncertain_labels = set(np.unique(gti[uncertain.astype(np.bool)]))
    # Any gt-building less than 100px or at the boundary is uncertain.
    for label, rc_arr in true_rcs_arr.items():
        if len(rc_arr) < MIN_SIZE:
            rc_arr = np.array(list(rc_arr))
            if (np.any(rc_arr == 0) or np.any(rc_arr == 2047)):
                uncertain_labels.add(label)
            else:
                rc_loc = tuple(rc_arr.T)
                is_invisible = (dsm[rc_loc] == DSM_NAN)
                if np.any(is_invisible):
                    invisible_rc = rc_arr.compress(is_invisible, axis=0)
                    invisible_rc_set = set(map(tuple, invisible_rc))
                    # Remove invisible pixels
                    remain_rc_set = list(set(map(tuple, rc_arr)).difference(invisible_rc_set))
                    true_rcs_arr[label] = np.array(remain_rc_set)
                    uncertain_labels.add(label)

    def make_int_coords(rc_arr, unique_labels, groupxs):
        # using nums instead of tuples gives the intersection a modest speedup
        rc_int = rc_arr.T[0] + pred.shape[0] + rc_arr.T[1]
        id_to_rc_int = ub.odict(zip(unique_labels,
                                    map(set, util.apply_grouping(rc_int, groupxs))))
        return id_to_rc_int

    # Make intersection a bit faster by filtering via bbox fist
    true_rcs_bbox = ub.map_vals(_bbox, true_rcs_arr)
    pred_rcs_bbox = ub.map_vals(_bbox, pred_rcs_arr)

    true_bboxes = np.array(list(true_rcs_bbox.values()))
    pred_bboxes = np.array(list(pred_rcs_bbox.values()))

    candidate_matches = {}
    for plabel, pb in zip(group_pred_labels, pred_bboxes):
        irc1 = np.maximum(pb[0:2], true_bboxes[:, 0:2])
        irc2 = np.minimum(pb[2:4], true_bboxes[:, 2:4])
        irc1 = np.minimum(irc1, irc2, out=irc1)
        isect_area = np.prod(np.abs(irc2 - irc1), axis=1)
        tlabels = list(ub.take(group_true_labels, np.where(isect_area)[0]))
        candidate_matches[plabel] = set(tlabels)

    # using nums instead of tuples gives the intersection a modest speedup
    pred_rcs_ = make_int_coords(pred_rc_arr, group_pred_labels, pred_groupxs)
    true_rcs_ = make_int_coords(true_rc_arr, group_true_labels, true_groupxs)

    # Greedy matching
    unused_true_rcs = true_rcs_.copy()
    FP = TP = FN = 0
    unused_true_keys = set(unused_true_rcs.keys())

    assignment = []
    fp_labels = []
    fn_labels = []
    tp_labels = []

    for pred_label, pred_rc_set in pred_rcs_.items():

        best_score = (-np.inf, -np.inf)
        best_label = None

        # Only check unused true labels that intersect with the predicted bbox
        true_cand = candidate_matches[pred_label] & unused_true_keys
        for true_label in true_cand:
            true_rc_set = unused_true_rcs[true_label]
            n_isect = len(pred_rc_set.intersection(true_rc_set))
            iou = n_isect / (len(true_rc_set) + len(pred_rc_set) - n_isect)
            if iou > MIN_IOU:
                score = (iou, -true_label)
                if score > best_score:
                    best_score = score
                    best_label = true_label

        if best_label is not None:
            assignment.append((pred_label, best_label, best_score[0]))
            unused_true_keys.remove(best_label)
            if true_label not in uncertain_labels:
                TP += 1
                tp_labels.append((pred_label, best_label, best_score[0]))
        else:
            FP += 1
            fp_labels.append(pred_label)

    # Had two bugs:
    # * used wrong variable to count false negs (all true were labeled as FN)
    #   (massivly increasing FN)
    # * Certain true building as marked as uncertain, but I was checking
    #   against the pred labels instead (possibly decreasing/increasing TP)

    fn_labels = unused_true_keys - uncertain_labels  # NOQA
    FN = len(fn_labels)

    precision = TP / (TP + FP) if TP > 0 else 0
    recall = TP / (TP + FN) if TP > 0 else 0
    if precision > 0 and recall > 0:
        f_score = 2 * precision * recall / (precision + recall)
    else:
        f_score = 0

    # They multiply by 1e6, but lets not do that.
    if info:
        infod = {
            'assign': assignment,
            'tp': tp_labels,
            'fp': fp_labels,
            'fn': fn_labels,
            'uncertain': uncertain_labels,
        }
        return (f_score, precision, recall), infod

    return (f_score, precision, recall)


if __name__ == '__main__':
    r"""
    CommandLine:
        python -m clab.live.urban_mapper
    """
    import xdoctest
    xdoctest.doctest_module(__file__)
