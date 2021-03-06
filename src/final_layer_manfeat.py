# coding=utf-8
# manfeat.py: classifier based on manually extracted features.

from __future__ import print_function
import argparse
import os
import cPickle
import itertools
from datetime import datetime

import numpy as np
from scipy.stats import mode
from keras.optimizers import Adam
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

from models.shallow import ShallowNet


SPLIT_DIR = "data/perssplit"
SPLITS = ["train", "val", "test"]
PICKLED_LABEL_FILE = "data/labels.pickle"
PERS_FIELD_NAME = "Answer.q7_persuasive"


def eval_pred(y, pred):
    acc = accuracy_score(y, pred)
    prec = precision_score(y, pred)
    rec = recall_score(y, pred)
    f1 = f1_score(y, pred)
    return {"acc": acc, "prec": prec, "rec": rec, "f1": f1}


def eval_model(model, batch_size, X, y):
    pred = model.predict_classes(X=X, batch_size=batch_size, verbose=0)
    return eval_pred(y, pred)


arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("--feats-file", type=str, required=True)
arg_parser.add_argument("--names-file", type=str, required=True)
arg_parser.add_argument("--sig-feats-file", type=str, default=None)
arg_parser.add_argument("--last-layer-file", type=str, default=None)
arg_parser.add_argument("--save-path", type=str, required=True)
arg_parser.add_argument("--train", type=str, choices=["true", "false"], required=True)
arg_parser.add_argument("--weights", type=str, default=None)
arg_parser.add_argument("--lr", type=float, nargs="+", required=True)
arg_parser.add_argument("--epochs", type=int, nargs="+", required=True)
arg_parser.add_argument("--dropout", type=float, nargs="+", required=True)
arg_parser.add_argument("--dense-layers", type=int, nargs="+", required=True)
arg_parser.add_argument("--dense-layer-units", type=int, nargs="+", required=True)
arg_parser.add_argument("--batch-size", type=int, nargs="+", required=True)
arg_parser.add_argument("--ensemble-size", type=int, required=True)
args = arg_parser.parse_args()

with open(PICKLED_LABEL_FILE, "rb") as lf:
    labels_map = cPickle.load(lf)

name_splits = {}
Xs = {}
ys = {}
for split in SPLITS:
    with open(os.path.join(SPLIT_DIR, "{}.txt".format(split))) as split_file:
        for line in split_file:
            name_splits[line.strip()] = split
    Xs[split] = []
    ys[split] = []

with open(args.names_file) as man_feats_names_file, open(args.feats_file) as feats_file:
    for name_line, feat_line in zip(man_feats_names_file, feats_file):
        name = name_line.strip()
        feats = map(float, feat_line.strip().split(","))
        split = name_splits[name]
        Xs[split].append(feats)
        score = labels_map[name][PERS_FIELD_NAME]
        if score >= 5.5:
            ys[split].append(1)
        else:
            ys[split].append(0)

for split in SPLITS:
    Xs[split] = np.array(Xs[split])
    ys[split] = np.array(ys[split])

if args.sig_feats_file is not None:
    print("Selecting significant features")
    with open(args.sig_feats_file) as sig_feats_file:
        sig_feats = [int(line.strip()) - 1 for line in sig_feats_file]
    for split in SPLITS:
        Xs[split] = Xs[split][:, sig_feats]

if args.train == "true":
    date = str(datetime.now().date())
    base_save_dir = os.path.join(args.save_path, date)
    os.makedirs(base_save_dir)

    final_train_perfs = {}
    final_val_perfs = {}
    for lr, epochs, dropout, dense_layers, dense_layer_units, batch_size in itertools.product(args.lr, args.epochs, args.dropout, args.dense_layers, args.dense_layer_units, args.batch_size):
        params = lr, epochs, dropout, dense_layers, dense_layer_units, batch_size
        print("LR: {}, EPOCHS: {}, DROPOUT: {}, DENSE LAYERS: {}, DENSE_LAYER_UNITS: {}, BATCH_SIZE: {}".format(*params))
        save_path = os.path.join(base_save_dir, "lr{};epochs{};dropout{};dense_layers{};dense_layer_units{};batch_size{}".format(*params))
        os.makedirs(save_path)

        train_preds = np.zeros((Xs["train"].shape[0], args.ensemble_size))
        val_preds = np.zeros((Xs["val"].shape[0], args.ensemble_size))
    
        print("Building model")
        model = ShallowNet(Xs["train"].shape[1], dropout, dense_layers, dense_layer_units, args.weights)
        model.compile(optimizer=Adam(lr=lr), loss="binary_crossentropy")
        print("Model built")

        history = model.fit(
            X=Xs["train"],
            y=ys["train"],
            batch_size=batch_size,
            nb_epoch=epochs,
            verbose=1,
            validation_data=(Xs["val"], ys["val"]),
            shuffle=True,
            show_accuracy=True,
        )

        model.layers.pop()
        model.compile(optimizer=Adam(lr=lr), loss="binary_crossentropy")
        train_pred = model.predict(X=Xs["train"], batch_size=batch_size, verbose=0)
        val_pred = model.predict(X=Xs["val"], batch_size=batch_size, verbose=0)
        cou = 0
        with open(args.last_layer_file, "w") as layer_file:
        	for vec in train_pred:
        	    layer_file.write(",".join([str(i) for i in vec]))
        	    layer_file.write("\n")
                    cou += 1
        	for vec in val_pred:
        	    layer_file.write(",".join([str(i) for i in vec]))
        	    layer_file.write("\n")
                    cou += 1
        print(cou)

        with open(args.last_layer_file+".labels", "w") as label_file:
        	for value in ys["train"]:
        		label_file.write(str(value))
        		label_file.write("\n")
        	for value in ys["val"]:
        		label_file.write(str(value))
        		label_file.write("\n")
        exit(1)

        final_train_pred = mode(train_preds, axis=1).mode
        final_val_pred = mode(val_preds, axis=1).mode
        final_train_perfs[params] = eval_pred(ys["train"], final_train_pred)
        final_val_perfs[params] = eval_pred(ys["val"], final_val_pred)
        print("final train perf: acc {}, f1 {}; final val perf: acc {}, f1 {}".format(final_train_perfs[params]["acc"], final_train_perfs[params]["f1"], final_val_perfs[params]["acc"], final_val_perfs[params]["f1"]))

    print("\n".join(map(lambda x: "{}: {}".format(x[0], x[1]), final_train_perfs.items())), file=open(os.path.join(base_save_dir, "final_train_perfs.txt"), "w"))
    print("\n".join(map(lambda x: "{}: {}".format(x[0], x[1]), final_val_perfs.items())), file=open(os.path.join(base_save_dir, "final_val_perfs.txt"), "w"))

    best_params = max(final_val_perfs, key=lambda x: final_val_perfs[x]["f1"])
else:
    best_params = (0.0001, 100, 0.5, 5, 5, 100)

best_lr, best_epochs, best_dropout, best_dense_layers, best_dense_layer_units, best_batch_size = best_params

if args.train == "true":
    print("Training ensemble on training and validation set")
    save_path = os.path.join(base_save_dir, "best_params")
    os.makedirs(save_path)

    preds = np.zeros((Xs["test"].shape[0], args.ensemble_size))
    for i in range(args.ensemble_size):
        print("Building model")
        model = ShallowNet(Xs["train"].shape[1], best_dropout, best_dense_layers, best_dense_layer_units, args.weights)
        model.compile(optimizer=Adam(lr=best_lr), loss="binary_crossentropy")
        print("Model built")

        history = model.fit(
            X=np.concatenate((Xs["train"], Xs["val"])),
            y=np.concatenate((ys["train"], ys["val"])),
            batch_size=best_batch_size,
            nb_epoch=best_epochs,
            verbose=1,
            shuffle=True,
            show_accuracy=True,
        )

        model.save_weights(os.path.join(save_path, "weights{}.h5".format(i)), overwrite=True)
        print("\n".join(map(str, history.history["acc"])), file=open(os.path.join(save_path, "train_accs{}.txt".format(i)), "w"))
        print("\n".join(map(str, history.history["loss"])), file=open(os.path.join(save_path, "train_losses{}.txt".format(i)), "w"))

        pred = model.predict_classes(X=Xs["test"], batch_size=batch_size, verbose=0)
        preds[:, i] = pred[:, 0]

    final_pred = mode(preds, axis=1).mode
    test_perf = eval_pred(ys["test"], final_pred)
else:
    print("Building model")
    model = ShallowNet(Xs["train"].shape[1], best_dropout, best_dense_layers, best_dense_layer_units, args.weights)
    model.compile(optimizer=Adam(lr=best_lr), loss="binary_crossentropy")
    print("Model built")

    test_perf = eval_model(model, best_batch_size, Xs["test"], ys["test"])

print("Test perf: {}".format(test_perf))

if args.train == "true":
    summary = {
        "best_lr": best_lr,
        "best_epochs": best_epochs,
        "best_dropout":  best_dropout,
        "best_dense_layers": best_dense_layers,
        "best_dense_layer_units": best_dense_layer_units,
        "best_batch_size": best_batch_size,
        "ensemble_size": args.ensemble_size,
        "test_perf": test_perf
    }
    print("\n".join(map(lambda x: "{}: {}".format(x[0], x[1]), summary.items())), file=open(os.path.join(base_save_dir, "summary.txt"), "w"))
