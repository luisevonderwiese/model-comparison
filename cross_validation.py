from Bio import AlignIO
from Bio.Align import MultipleSeqAlignment
from Bio.SeqRecord import SeqRecord
from Bio.AlignIO.PhylipIO import RelaxedPhylipWriter
import random
import os
import math
import numpy as np
from tabulate import tabulate
import matplotlib.pyplot as plt
import matplotlib

def split_indices(num_sites, num_samples = 10, ratio = 0.6):
    num_sites_train = math.ceil(num_sites * ratio)
    res = []
    for i in range(num_samples):
        l = [_ for _ in range(num_sites)]
        random.shuffle(l)
        train_indices = l[:num_sites_train]
        res.append(train_indices)
    return res


def empty_align(ref_align):
    new_records = [SeqRecord("", id=ref_align[i].id) for i in range(len(ref_align))]
    return MultipleSeqAlignment(new_records, annotations={}, column_annotations={})

def concat_align(a1, a2):
    new_sequences = []
    assert(len(a1) == len(a2))
    for i in range(len(a1)):
        seq1 = a1[i].seq
        seq2 = a2[i].seq
        new_sequences.append(seq1 + seq2)
    new_records = [SeqRecord(new_sequences[i], id=a1[i].id) for i in range(len(a1))]
    return MultipleSeqAlignment(new_records, annotations={}, column_annotations={})



def run_inference(msa_path, model, prefix, args = ""):
    if not os.path.isfile(msa_path):
        print("MSA " + msa_path + " does not exist")
        return
    prefix_dir = "/".join(prefix.split("/")[:-1])
    if not os.path.isdir(prefix_dir):
        os.makedirs(prefix_dir)
    if not os.path.isfile(prefix + ".raxml.bestTree"):
        args = args + " --redo"
    command = "./bin/raxml-ng-multiple-force"
    command += " --msa " + msa_path
    command += " --model " + model
    command += " --prefix " + prefix
    command += " --threads auto --seed 2 --force model_lh_impr -blopt nr_safe"
    command += " " + args
    os.system(command)


def run_evaluate(msa_path, prefix, ref_prefix, args = ""):
    if not os.path.isfile(msa_path):
        print("MSA " + msa_path + " does not exist")
        return
    prefix_dir = "/".join(prefix.split("/")[:-1])
    if not os.path.isdir(prefix_dir):
        os.makedirs(prefix_dir)
    if not os.path.isfile(ref_prefix + ".raxml.bestModel"):
        return
    with open(ref_prefix + ".raxml.bestModel", "r") as model_file:
        model =  model_file.readlines()[0].split(",")[0]
    command = "./bin/raxml-ng-multiple-force --evaluate "
    command += " --msa " + msa_path
    command += " --tree " + ref_prefix + ".raxml.bestTree"
    command += " --model " + model
    command += " --prefix " + prefix
    command += " --threads auto --seed 2 --opt-model off --opt-branches off"
    command += " " + args
    os.system(command)


def final_llh(prefix):
    if not os.path.isfile(prefix + ".raxml.log"):
        return float("nan")
    with open(prefix + ".raxml.log", "r") as logfile:
        lines = logfile.readlines()
    for line in lines:
        if line.startswith("Final LogLikelihood: "):
            return float(line.split(": ")[1])
    return float('nan')

def relative_llh(msa_path, prefix, kappa, model):
    with open(msa_path, "r") as msa_file:
        num_sites = int(msa_file.readlines()[0].split(" ")[2])
    if model == "BIN":
        num_sites = int(num_sites / kappa)
    return final_llh(prefix) / num_sites
    #return final_llh(prefix)

def create_samples(kappa, msa_dir):
    bin_msa_type = "bin_part_" + str(kappa)
    prototype_msa_type = "prototype_part_" + str(kappa)
    bin_msa_path = os.path.join(msa_dir, bin_msa_type + ".phy")
    prototype_msa_path = os.path.join(msa_dir, prototype_msa_type + ".phy")
    with open(prototype_msa_path, "r") as msa_file:
        num_sites = int(msa_file.readlines()[0].split(" ")[2])
    with open(bin_msa_path, "r") as msa_file:
        num_sites_bin = int(msa_file.readlines()[0].split(" ")[2])
    assert(num_sites_bin == kappa * num_sites)
    try:
        bin_align = AlignIO.read(bin_msa_path, "phylip-relaxed")
    except:
        print(msa_dir, "Failed")
        return False
    try:
        prototype_align = AlignIO.read(bin_msa_path, "phylip-relaxed")
    except:
        print(msa_dir, "Failed")
        return False
    indices_list = split_indices(num_sites)
    for (t, train_indices) in enumerate(indices_list):
        bin_train_align = empty_align(bin_align)
        bin_test_align = empty_align(bin_align)
        prototype_train_align = empty_align(prototype_align)
        prototype_test_align = empty_align(prototype_align)
        for s in range(num_sites):
            if s in train_indices :
                prototype_train_align = concat_align(prototype_train_align, prototype_align[:, s:s+1])
                bin_train_align = concat_align(bin_train_align, bin_align[:, s*kappa : (s+1) * kappa])
            else:
                prototype_test_align = concat_align(prototype_test_align, prototype_align[:, s:s+1])
                bin_test_align = concat_align(bin_test_align, bin_align[:, s*kappa : (s+1) * kappa])
        with open(os.path.join(msa_dir, bin_msa_type + "_cv_train_" + str(t) + ".phy"),"w+") as f:
            writer = RelaxedPhylipWriter(f)
            writer.write_alignment(bin_train_align)
        with open(os.path.join(msa_dir, bin_msa_type + "_cv_test_" + str(t) + ".phy"),"w+") as f:
            writer = RelaxedPhylipWriter(f)
            writer.write_alignment(bin_test_align)
        with open(os.path.join(msa_dir, prototype_msa_type + "_cv_train_" + str(t) + ".phy"),"w+") as f:
            writer = RelaxedPhylipWriter(f)
            writer.write_alignment(prototype_train_align)
        with open(os.path.join(msa_dir, prototype_msa_type + "_cv_test_" + str(t) + ".phy"),"w+") as f:
            writer = RelaxedPhylipWriter(f)
            writer.write_alignment(prototype_test_align)
    print(msa_dir, "done")
    return True


def train_raxml_ng(msa_dir, target_dir, kappa):
    bin_msa_type = "bin_part_" + str(kappa)
    prototype_msa_type = "prototype_part_" + str(kappa)
    x = int(math.pow(2, kappa))
    for t in range(10):
        bin_msa_path = os.path.join(msa_dir, bin_msa_type + "_cv_train_" + str(t) + ".phy")
        bin_prefix = os.path.join(target_dir, bin_msa_type + "_cv_train_" + str(t) + "_BIN")
        run_inference(bin_msa_path, "BIN", bin_prefix)
        prototype_msa_path = os.path.join(msa_dir, bin_msa_type + "_cv_train_" + str(t) + ".phy")
        prototype_prefix = os.path.join(target_dir, prototype_msa_type + "_cv_train_" + str(t) + "_COG")
        run_inference(prototype_msa_path, "COG" + str(x), prototype_prefix)
        gtr_prefix = os.path.join(target_dir, prototype_msa_type + "_cv_train_" + str(t) + "_GTR")
        run_inference(prototype_msa_path, "MULTI" + str(x - 1) + "_GTR", gtr_prefix)
        mk_prefix = os.path.join(target_dir, prototype_msa_type + "_cv_train_" + str(t) + "_MK")
        run_inference(prototype_msa_path, "MULTI" + str(x - 1) + "_MK", mk_prefix)



def test_raxml_ng(msa_dir, target_dir, kappa):
    bin_msa_type = "bin_part_" + str(kappa)
    prototype_msa_type = "prototype_part_" + str(kappa)
    x = int(math.pow(2, kappa))
    for t in range(10):
        bin_msa_path = os.path.join(msa_dir, bin_msa_type + "_cv_test_" + str(t) + ".phy")
        bin_prefix = os.path.join(target_dir, bin_msa_type + "_cv_train_" + str(t) + "_BIN")
        bin_test_prefix = os.path.join(target_dir, bin_msa_type + "_cv_test_" + str(t) + "_BIN")
        run_evaluate(bin_msa_path, bin_test_prefix, bin_prefix)
        prototype_msa_path = os.path.join(msa_dir, bin_msa_type + "_cv_test_" + str(t) + ".phy")
        prototype_prefix = os.path.join(target_dir, prototype_msa_type + "_cv_train_" + str(t) + "_COG")
        prototype_test_prefix = os.path.join(target_dir, prototype_msa_type + "_cv_test_" + str(t) + "_COG")
        run_evaluate(prototype_msa_path, prototype_test_prefix, prototype_prefix)
        gtr_prefix = os.path.join(target_dir, prototype_msa_type + "_cv_train_" + str(t) + "_GTR")
        gtr_test_prefix = os.path.join(target_dir, prototype_msa_type + "_cv_test_" + str(t) + "_GTR")
        run_evaluate(prototype_msa_path, gtr_test_prefix, gtr_prefix)
        mk_prefix = os.path.join(target_dir, prototype_msa_type + "_cv_train_" + str(t) + "_MK")
        mk_test_prefix = os.path.join(target_dir, prototype_msa_type + "_cv_test_" + str(t) + "_MK")
        run_evaluate(prototype_msa_path, mk_test_prefix, mk_prefix)



def analysis(msa_dir, target_dir, kappa):
    bin_msa_type = "bin_part_" + str(kappa)
    prototype_msa_type = "prototype_part_" + str(kappa)
    results = [[] for _ in range(8)]
    for t in range(10):
        for m, (model, msa_type) in enumerate([("BIN", bin_msa_type), ("COG", prototype_msa_type), ("GTR", prototype_msa_type), ("MK", prototype_msa_type)]):
            train_msa_path = os.path.join(msa_dir, msa_type + "_cv_train_" + str(t) + ".phy")
            train_prefix = os.path.join(target_dir, msa_type + "_cv_train_" + str(t) + "_" + model)
            results[m * 2].append(relative_llh(train_msa_path, train_prefix, kappa, model))
            test_msa_path = os.path.join(msa_dir, msa_type + "_cv_test_" + str(t) + ".phy")
            test_prefix = os.path.join(target_dir, msa_type + "_cv_test_" + str(t) + "_" + model)
            results[m * 2 + 1].append(relative_llh(test_msa_path, test_prefix, kappa, model))
    return [sum(el) / len(el) for el in results]


def differences_analysis(msa_dir, target_dir, kappa):
    bin_msa_type = "bin_part_" + str(kappa)
    prototype_msa_type = "prototype_part_" + str(kappa)
    results = [[] for _ in range(4)]
    for t in range(10):
        for m, (model, msa_type) in enumerate([("BIN", bin_msa_type), ("COG", prototype_msa_type), ("GTR", prototype_msa_type), ("MK", prototype_msa_type)]):
            train_msa_path = os.path.join(msa_dir, msa_type + "_cv_train_" + str(t) + ".phy")
            train_prefix = os.path.join(target_dir, msa_type + "_cv_train_" + str(t) + "_" + model)
            rel_train_llh = relative_llh(train_msa_path, train_prefix, kappa, model)
            test_msa_path = os.path.join(msa_dir, msa_type + "_cv_test_" + str(t) + ".phy")
            test_prefix = os.path.join(target_dir, msa_type + "_cv_test_" + str(t) + "_" + model)
            rel_test_llh = relative_llh(test_msa_path, test_prefix, kappa, model)
            results[m].append((rel_train_llh - rel_test_llh) / rel_train_llh)
            #results[m].append(rel_train_llh - rel_test_llh)
    return [sum(el) / len(el) for el in results]


def plots(msa_dir, target_dir, kappa, plots_super_dir, ds_name):
    bin_msa_type = "bin_part_" + str(kappa)
    prototype_msa_type = "prototype_part_" + str(kappa)
    ind = np.arange(10)
    width = 0.1
    offsets = [-0.35, -0.25, -0.15, -0.05, 0.05, 0.15, 0.25, 0.35]
    cmap_train = matplotlib.cm.get_cmap('Set1')
    cmap_test = matplotlib.cm.get_cmap('Pastel1')
    bin_msa_type = "bin_part_" + str(kappa)
    prototype_msa_type = "prototype_part_" + str(kappa)
    results = [[] for _ in range(8)]
    plots_dir = os.path.join(plots_super_dir, str(kappa))
    if not os.path.isdir(plots_dir):
        os.makedirs(plots_dir)
    for t in range(10):
        for m, (model, msa_type) in enumerate([("BIN", bin_msa_type), ("COG", prototype_msa_type), ("GTR", prototype_msa_type), ("MK", prototype_msa_type)]):
            train_msa_path = os.path.join(msa_dir, msa_type + "_cv_train_" + str(t) + ".phy")
            train_prefix = os.path.join(target_dir, msa_type + "_cv_train_" + str(t) + "_" + model)
            results[m * 2].append(relative_llh(train_msa_path, train_prefix, kappa, model))
            test_msa_path = os.path.join(msa_dir, msa_type + "_cv_test_" + str(t) + ".phy")
            test_prefix = os.path.join(target_dir, msa_type + "_cv_test_" + str(t) + "_" + model)
            results[m * 2 + 1].append(relative_llh(test_msa_path, test_prefix, kappa, model))
    fig, ax = plt.subplots()
    ax.bar(ind + offsets[0], results[0], width, label='train BIN', color = cmap_train(0))
    ax.bar(ind + offsets[1], results[1], width, label='test BIN', color = cmap_test(0))
    ax.bar(ind + offsets[2], results[2], width, label='train COG', color = cmap_train(1))
    ax.bar(ind + offsets[3], results[3], width, label='test COG', color = cmap_test(1))
    ax.bar(ind + offsets[4], results[4], width, label='train GTR', color = cmap_train(2))
    ax.bar(ind + offsets[5], results[5], width, label='test GTR', color = cmap_test(2))
    ax.bar(ind + offsets[6], results[6], width, label='train GTR', color = cmap_train(3))
    ax.bar(ind + offsets[7], results[7], width, label='test GTR', color = cmap_test(3))
    ax.set_ylabel('relative llh')
    ax.set_xticks(ind)
    ax.set_xticklabels(range(10))
    ax.legend()
    plt.savefig(os.path.join(plots_dir, ds_name  + ".png"))
    plt.clf()
    plt.close()






msa_super_dir = "data/lingdata_cognate/msa"
raxmlng_super_dir = "data/cross_validation"
plots_super_dir = "data/cross_validation_plots"
kappa = 3 
random.seed(2)
all_res = []
all_diff_res = []
headers = ("dataset", "train_BIN", "test_BIN", "train_COG", "test_COG", "train_GTR", "test_GTR", "train_MK", "test_MK")
diff_headers = ("dataset", "diff_BIN", "diff_COG", "diff_GTR", "diff_MK")
for ds_name in os.listdir(msa_super_dir):
    msa_dir = os.path.join(msa_super_dir, ds_name)
    target_dir = os.path.join(raxmlng_super_dir, ds_name)
    bin_msa_type = "bin_part_" + str(kappa)
    prototype_msa_type = "prototype_part_" + str(kappa)
    bin_msa_path = os.path.join(msa_dir, bin_msa_type + ".phy")
    prototype_msa_path = os.path.join(msa_dir, prototype_msa_type + ".phy")
    if not os.path.isfile(bin_msa_path) or not os.path.isfile(prototype_msa_path):
        continue
    success = create_samples(kappa, msa_dir)
    if not success:
        continue
    #train_raxml_ng(msa_dir, target_dir, kappa)
    #test_raxml_ng(msa_dir, target_dir, kappa)
    all_res.append([ds_name] + analysis(msa_dir, target_dir, kappa))
    all_diff_res.append([ds_name] + differences_analysis(msa_dir, target_dir, kappa))
    plots(msa_dir, target_dir, kappa, plots_super_dir, ds_name)
print(tabulate(all_res, tablefmt="pipe", headers = headers))
print(tabulate(all_diff_res, tablefmt="pipe", headers = diff_headers))