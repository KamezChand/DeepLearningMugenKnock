import chainer
import chainer.links as L
import chainer.functions as F
import argparse
import cv2
import numpy as np
from glob import glob
import matplotlib.pyplot as plt

num_classes = 2
img_height, img_width = 64, 64#572, 572
out_height, out_width = 64, 64#388, 388
GPU = -1
    
class Mynet(chainer.Chain):
    def __init__(self, train=False):
        self.train = train
        super(Mynet, self).__init__()
        with self.init_scope():
            self.enc1 = chainer.Sequential()
            for i in range(2):
                self.enc1.append(L.Convolution2D(None, 32, ksize=3, pad=1, stride=1, nobias=True))
                self.enc1.append(F.relu)
                self.enc1.append(L.BatchNormalization(32))

            self.enc2 = chainer.Sequential()
            for i in range(2):
                self.enc2.append(L.Convolution2D(None, 32, ksize=3, pad=1, stride=1, nobias=True))
                self.enc2.append(F.relu)
                self.enc2.append(L.BatchNormalization(32))

            self.dec1 = chainer.Sequential()
            for i in range(2):
                self.dec1.append(L.Convolution2D(None, 32, ksize=3, pad=1, stride=1, nobias=True))
                self.dec1.append(F.relu)
                self.dec1.append(L.BatchNormalization(32))
                
            self.out = L.Convolution2D(None, num_classes+1, ksize=1, pad=0, stride=1, nobias=False)
        
    def forward(self, x):
        # block conv1
        x = self.enc1(x)
        x = F.max_pooling_2d(x, ksize=2, stride=2)

        x = self.enc2(x)

        mb, c, h, w = x.shape
        x = chainer.functions.resize_images(x, output_shape=[h*2, w*2])

        x = self.dec1(x)
        
        x = self.out(x)
        return x

    
CLS = {'akahara': [0,0,128],
       'madara': [0,128,0]}
    
# get train data
def data_load(path, hf=False, vf=False):
    xs = []
    ts = []
    paths = []
    
    for dir_path in glob(path + '/*'):
        for path in glob(dir_path + '/*'):
            x = cv2.imread(path)
            x = cv2.resize(x, (img_width, img_height)).astype(np.float32)
            x /= 255.
            x = x[..., ::-1]
            xs.append(x)

            gt_path = path.replace("images", "seg_images").replace(".jpg", ".png")
            gt = cv2.imread(gt_path)
            gt = cv2.resize(gt, (out_width, out_height), interpolation=cv2.INTER_NEAREST)

            t = np.zeros((out_height, out_width), dtype=np.int)

            for i, (_, vs) in enumerate(CLS.items()):
                ind = (gt[...,0] == vs[0]) * (gt[...,1] == vs[1]) * (gt[...,2] == vs[2])
                t[ind] = i + 1

            #print(gt_path)
            #import matplotlib.pyplot as plt
            #plt.imshow(t, cmap='gray')
            #plt.show()

            ts.append(t)
            
            paths.append(path)

            if hf:
                xs.append(x[:, ::-1])
                ts.append(t[:, ::-1])
                paths.append(path)

            if vf:
                xs.append(x[::-1])
                ts.append(t[::-1])
                paths.append(path)

            if hf and vf:
                xs.append(x[::-1, ::-1])
                ts.append(t[::-1, ::-1])
                paths.append(path)

    xs = np.array(xs)
    ts = np.array(ts)

    xs = xs.transpose(0,3,1,2)

    return xs, ts, paths


# train
def train():
    # model
    model = Mynet(train=True)

    if GPU >= 0:
        chainer.cuda.get_device(GPU).use()
        model.to_gpu()
    
    opt = chainer.optimizers.MomentumSGD(0.01, momentum=0.9)
    opt.setup(model)
    #opt.add_hook(chainer.optimizer.WeightDecay(0.0005))

    xs, ts, paths = data_load('../Dataset/train/images/', hf=True, vf=True)

    # training
    mb = 4
    mbi = 0
    train_ind = np.arange(len(xs))
    np.random.seed(0)
    np.random.shuffle(train_ind)
    
    for i in range(500):
        if mbi + mb > len(xs):
            mb_ind = train_ind[mbi:]
            np.random.shuffle(train_ind)
            mb_ind = np.hstack((mb_ind, train_ind[:(mb-(len(xs)-mbi))]))
            mbi = mb - (len(xs) - mbi)
        else:
            mb_ind = train_ind[mbi: mbi+mb]
            mbi += mb

        x = xs[mb_ind]
        t = ts[mb_ind]
            
        if GPU >= 0:
            x = chainer.cuda.to_gpu(x)
            t = chainer.cuda.to_gpu(t)
        #else:
        #    x = chainer.Variable(x)
        #    t = chainer.Variable(t)

        y = model(x)

        #accu = F.accuracy(y, t[..., 0])
        y = F.transpose(y, axes=(0,2,3,1))
        y = F.reshape(y, [-1, num_classes+1])
        t = F.reshape(t, [-1])
        loss = F.softmax_cross_entropy(y, t)
        accu = F.accuracy(y, t)

        model.cleargrads()
        loss.backward()
        opt.update()

        loss = loss.data
        accu = accu.data
        if GPU >= 0:
            loss = chainer.cuda.to_cpu(loss)
            accu = chainer.cuda.to_cpu(accu)
        
        print("iter >>", i+1, ',loss >>', loss.item(), ',accuracy >>', accu)

    chainer.serializers.save_npz('cnn.npz', model)

# test
def test():
    model = Mynet(train=False)

    if GPU >= 0:
        chainer.cuda.get_device_from_id(cf.GPU).use()
        model.to_gpu()

    ## Load pretrained parameters
    chainer.serializers.load_npz('cnn.npz', model)

    xs, ts, paths = data_load('../Dataset/test/images/')

    for i in range(len(paths)):
        x = xs[i]
        t = ts[i]
        path = paths[i]
        
        x = np.expand_dims(x, axis=0)
        if GPU >= 0:
            x = chainer.cuda.to_gpu(x)

        pred = model(x)

        pred = F.transpose(pred, axes=(0,2,3,1))
        pred = F.reshape(pred, [-1, num_classes+1])
        pred = F.softmax(pred)
        pred = F.reshape(pred, [-1, out_height, out_width, num_classes+1])
        
        if GPU >= 0:
            pred = chainer.cuda.to_cpu(pred)
        pred = pred.data[0]
        pred = pred.argmax(axis=-1)

        # visualize
        out = np.zeros((out_height, out_width, 3), dtype=np.uint8)
        for i, (_, vs) in enumerate(CLS.items()):
            out[pred == (i+1)] = vs
        
        x = chainer.cuda.to_cpu(x) if GPU >= 0 else x
        plt.subplot(1,2,1)
        plt.imshow(x[0].transpose(1,2,0))
        plt.title("input")
        plt.subplot(1,2,2)
        plt.imshow(out[..., ::-1])
        plt.title("predicted")
        plt.show()

        print("in {}".format(path))
    

def arg_parse():
    parser = argparse.ArgumentParser(description='CNN implemented with Keras')
    parser.add_argument('--train', dest='train', action='store_true')
    parser.add_argument('--test', dest='test', action='store_true')
    args = parser.parse_args()
    return args

# main
if __name__ == '__main__':
    args = arg_parse()

    if args.train:
        train()
    if args.test:
        test()

    if not (args.train or args.test):
        print("please select train or test flag")
        print("train: python main.py --train")
        print("test:  python main.py --test")
        print("both:  python main.py --train --test")
