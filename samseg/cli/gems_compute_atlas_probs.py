#!/usr/bin/env python

###########################
#
# Compute mesh node probabilities (alphas) from "ground truth" segmentation images using estimated node deformations.
# Node probabilities are estimated using an expectation maximization (EM) algorithm.
#
# The script requires that SAMSEG has been run with the --history flag on the subjects of interest
# The script works with 1 or more structures.
# For estimating mesh node probabilities for more than one structure
# the --multi-structure flag should be on and a list of labels should be given as input using the flag --labels
#
###########################

import sys
import os
import numpy as np
import nibabel as nib
import surfa as sf
import time
import argparse
import samseg
from samseg import gems

def parseArguments(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--subjects-dir', help='Directory with saved SAMSEG runs with --history flag.', required=True)
    parser.add_argument('--mesh-collections', nargs='+', help='Mesh collection file(s).', required=True)
    parser.add_argument('--out-dir', help='Output directory.', required=True)
    parser.add_argument('--segmentations-dir', help='Directory with GT segmentations.')
    parser.add_argument('--gt-from-FS', action='store_true', default=False, help='GT from FreeSurfer segmentations.')
    parser.add_argument('--segmentation-name', default='aseg.mgz',help='Filename of the segmentations, assumed to be the same for each subject.')
    parser.add_argument('--multi-structure', action='store_true', default=False, help="Estimate alphas from more than 1 structure.")
    parser.add_argument('--labels', type=int, nargs='+', help="Labels numbers. Needs --multi-structure flag on.")
    parser.add_argument('--from-samseg', action='store_true', default=False, help="SAMSEG runs obtained from command samseg instead of run_samseg.")
    parser.add_argument('--EM-iterations', type=int, default=10, help="EM iterations.")
    parser.add_argument('--show-figs', action='store_true', default=False, help='Show figures during run.')
    parser.add_argument('--save-figs', action='store_true', default=False, help='Save rasterized prior of each subject.')
    parser.add_argument('--save-average-figs', action='store_true', default=False, help='Save average rasterized prior.')
    parser.add_argument('--subjects_file', help='Text file with list of subjects.')
    parser.add_argument('--labels_file', help='Text file with list of labels (instead of --labels).')
    parser.add_argument('--samseg-subdir', default='samseg',help='Name of samseg subdir in subject/mri folder')

    args = parser.parse_args()

    return args


def main():
    args = parseArguments(sys.argv[1:])

    if not os.path.exists(args.out_dir):
        os.makedirs(args.out_dir)

    if args.show_figs:
        visualizer = samseg.initVisualizer(True, True)
    else:
        visualizer = samseg.initVisualizer(False, False)

    if args.save_figs:
        import nibabel as nib

    if(args.subjects_file != None):
        with open(args.subjects_file) as f:
            lines = f.readlines();
            subject_list = [];
            for line in lines:
                subject_list.append(line.strip());
    else:
        subject_list = [pathname for pathname in os.listdir(args.subjects_dir) if os.path.isdir(os.path.join(args.subjects_dir, pathname))]
    subject_list.sort()
    number_of_subjects = len(subject_list)

    logfile = os.path.join(args.out_dir,'gems_compute_atlas_probs.log');
    logfp = open(logfile,"w")
    logfp.write("cd "+os.getcwd()+"\n");
    logfp.write(' '.join(sys.argv)+"\n")
    logfp.flush();

    outsubjectsfile = os.path.join(args.out_dir,'subjects.txt');
    with open(outsubjectsfile,"w") as f:
        for subject in subject_list:
            f.write(subject+"\n")

    if(args.labels_file == None):
        labels = args.labels;
    else:
        with open(args.labels_file) as f:
            lines = f.readlines();
            labels = [];
            for line in lines:
                for item in line.split():
                    labels.append(int(item))

    outlabelfile = os.path.join(args.out_dir,'labels.txt');
    with open(outlabelfile,"w") as f:
        for label in labels:
            f.write(str(label)+"\n")

    print("Labels")
    print(labels)

    if args.multi_structure:
        number_of_classes = len(labels) + 1 # + 1 for background
    else:
        number_of_classes = 2 # 1 is background

    # We need an init of the probabilistic segmentation class
    # to call instance methods
    atlas = samseg.ProbabilisticAtlas()

    t0 = time.time();
    for level, mesh_collection_file in enumerate(args.mesh_collections):

        print("Working on mesh collection at level " + str(level + 1))

        # Read mesh collection
        print("Loading mesh collection at: " + str(mesh_collection_file))
        mesh_collection = gems.KvlMeshCollection()
        mesh_collection.read(mesh_collection_file)

        # We are interested only on the reference mesh
        mesh = mesh_collection.reference_mesh
        number_of_nodes = mesh.point_count

        print('Number of subjects: ' + str(len(subject_list)))

        # Define what we are interesting in, i.e., the label statistics of the structure(s) of interest
        label_statistics_in_mesh_nodes = np.zeros([number_of_nodes, number_of_classes, number_of_subjects])
        
        for subject_number, subject_dir in enumerate(subject_list):
            
            # Show progress to anyone who's watching
            telapsed = (time.time()-t0)/60;
            print("====================================================================")
            print("")
            #print("Subject number: " + str(subject_number + 1)+"/"+str(number_of_subjects) + " "+ subject_dir + " " str(telapsed))
            print("Level %d Subject %d/%d %s %6.1f" % (level+1,subject_number+1,number_of_subjects,subject_dir,telapsed))
            print("")
            print("====================================================================")
            logfp.write("Level %d Subject %d/%d %s %6.1f\n" % (level+1,subject_number+1,number_of_subjects,subject_dir,telapsed))
            logfp.flush();

            # Read the manually annotated segmentation for the specific subject
            if args.gt_from_FS:
                segpath = os.path.join(args.segmentations_dir, subject_dir, 'mri', args.segmentation_name);
                print("seg %s" % segpath);
                segmentation_image = nib.load(segpath).get_fdata()
                affine = nib.load(os.path.join(args.segmentations_dir, subject_dir, 'mri', args.segmentation_name)).affine
            else:
                segmentation_image = nib.load(os.path.join(args.segmentations_dir, subject_dir, args.segmentation_name)).get_fdata()
                affine = nib.load(os.path.join(args.segmentations_dir, subject_dir, args.segmentation_name)).affine

            if args.from_samseg:
                history = np.load(os.path.join(args.subjects_dir, subject_dir, 'mri', args.samseg_subdir, 'history.p'), allow_pickle=True)
            else:
                history = np.load(os.path.join(args.subjects_dir, subject_dir, 'history.p'), allow_pickle=True)

            # Get the node positions in image voxels
            model_specifications = history['input']['modelSpecifications']
            transform_matrix = history['transform']
            transform = gems.KvlTransform(samseg.requireNumpyArray(transform_matrix))
            deformations = history['historyWithinEachMultiResolutionLevel'][level]['deformation']
            node_positions = atlas.getMesh(
                mesh_collection_file,
                transform,
                K=model_specifications.K,
                initialDeformation=deformations,
                initialDeformationMeshCollectionFileName=mesh_collection_file).points

            # The image is cropped as well so the voxel coordinates
            # do not exactly match with the original image,
            # i.e., there's a shift. Let's undo that.
            cropping = history['cropping']
            node_positions += [slc.start for slc in cropping]

            # Estimate n-class alphas representing the segmentation map, initialized with a flat prior
            segmentation_map = np.zeros([segmentation_image.shape[0], segmentation_image.shape[1], segmentation_image.shape[2],
                                         number_of_classes], np.uint16)
            if args.multi_structure:
                for label_number, label in enumerate(labels):
                    # + 1 here since we want background as first class
                    segmentation_map[:, :, :, label_number + 1] = (segmentation_image == label) * 65535
                # Make sure to fill what is left in background class
                segmentation_map[:, :, :, 0] = 65535 - np.sum(segmentation_map[:, :, :, 1:], axis=3)
            else:
                segmentation_map[:, :, :, 0] = (1 - segmentation_image) * 65535
                segmentation_map[:, :, :, 1] = segmentation_image * 65535

            mesh = mesh_collection.reference_mesh
            mesh.points = node_positions
            mesh.alphas = mesh.fit_alphas(segmentation_map, args.EM_iterations)

            # Show rasterized prior with updated alphas
            if args.show_figs:
                rasterized_prior = mesh.rasterize(segmentation_image.shape) / 65535
                rasterized_prior = rasterized_prior[:, :, :, 1:]  # No need to show background
                visualizer.show(images=rasterized_prior)
    
            # Save rasterized prior with updated alphas
            if args.save_figs:
                rasterized_prior = mesh.rasterize(segmentation_image.shape) / 65535
                rasterized_prior = rasterized_prior[:, :, :, 1:]  # No need to save background
                img = nib.Nifti1Image(rasterized_prior, affine)
                nib.save(img, os.path.join(args.out_dir, "level_" + str(level + 1) + "_rasterized_prior_sub" + str(subject_number + 1)))

            # Save label statistics of subject
            label_statistics_in_mesh_nodes[:, :, subject_number] = mesh.alphas.copy()

        # Show rasterized prior with alphas as mean
        if args.show_figs:
            mesh.alphas = np.mean(label_statistics_in_mesh_nodes, axis=2)
            rasterized_prior = mesh.rasterize(segmentation_image.shape) / 65535
            rasterized_prior = rasterized_prior[:, :, :, 1:] # No need to show background
            visualizer.show(images=rasterized_prior)

        # Save rasterized prior with alphas as mean
        if args.save_average_figs:

            mesh.alphas = np.mean(label_statistics_in_mesh_nodes, axis=2)
            rasterized_prior = mesh.rasterize(segmentation_image.shape) / 65535
            rasterized_prior = rasterized_prior[:, :, :, 1:] # No need to save background
            img = nib.Nifti1Image(rasterized_prior, np.eye(4))
            nib.save(img, os.path.join(args.out_dir, "level_" + str(level + 1) + "_average_rasterized_prior"))

        # Save label statistics in a npy file
        np.save(os.path.join(args.out_dir, "label_statistics_atlas_" + str(level + 1)), label_statistics_in_mesh_nodes)

    # end level loop

    logfp.write("gems_compute_atlas_probs done\n");
    logfp.close();
    print ("gems_compute_atlas_probs done");



if __name__ == '__main__':
    main()
