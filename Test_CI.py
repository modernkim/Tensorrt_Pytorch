import torch
import numpy as np
import time
import numpy as np
import torchvision
import torchvision.transforms as transforms
import torch.backends.cudnn as cudnn
import torch as quantization
from torch2trt import torch2trt
from fp16util import network_to_half
from models import *
from torch2trt import TRTModule
from torch.autograd import Variable
import copy
import argparse


parser = argparse.ArgumentParser(description='PyTorch CIFAR100 Test')
parser.add_argument('--batch_size', default=1, type=float, help='batch_size')
parser.add_argument('--network', default = ResNet_none_18(), type=bool,help='load your network')
parser.add_argument('--weight_path', default = './checkpoint/ResNet18_Single.pth', type=str,help='load_pth')
parser.add_argument('--trtFP', default = 16, type =int, help='trt_floating_point')
parser.add_argument('--trtbatch', default=1, type=int, help='trt_sample_img_batch')
parser.add_argument('--trtchannels', default=3, type=int, help='trt_sample_img_channels')
parser.add_argument('--trtpixels', default=32, type=int, help='trt_sample_img_pixels')
args = parser.parse_args()

device = 'cuda' if torch.cuda.is_available() else 'cpu'

# CIFAR100 data load & transforms
transform_test = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.5070751592371323, 0.48654887331495095, 0.4409178433670343), (0.2673342858792401, 0.2564384629170883, 0.27615047132568404)),
])
testset = torchvision.datasets.CIFAR100(root='./data', train=False, download=True, transform=transform_test)
testloader = torch.utils.data.DataLoader(testset, batch_size=args.batch_size, shuffle=False, num_workers=4)

#load model
print('==> Building Network..')
net = args.network
cudnn.benuchmark = True
net.load_state_dict(torch.load(args.weight_path))
net.to(device)

#check base model params
print('Total params: %.2fM' % (sum(p.numel() for p in net.parameters())/1000000.0))

FP32_time=[]
def FP32(epoch):
    print('=========Start_FP32_Check==========')
    net.eval()
    correct = 0
    total = 0
    avg_frame_total = 0.
    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(testloader):
            inputs, targets = inputs.to(device), targets.to(device)
            tic = time.time()
            outputs = net(inputs)
            toc = time.time()
            if batch_idx != 0:
                FP32_time.append(toc-tic)
                avg_frame_total += (FP32_time[-1])
                avg_frame = avg_frame_total/batch_idx
                avg_frame = 1/avg_frame
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()
            if ((batch_idx != 0) and (batch_idx%2000==0)) or batch_idx == 9999:
            	print(batch_idx, len(testloader), 'Acc: %.3f%% (%d/%d), FP32 Speed is : (%.3f [FPS]) '
            	% (100.*correct/total, correct, total, avg_frame))


def FP16(epoch): 
    half_net = args.network
    half_net.load_state_dict(torch.load(args.weight_path))
    half_net.half().to(device)
   
    print('=========Start_FP16_Check==========')
    half_net.eval()
    FP16_time = []
    correct = 0
    total = 0
    avg_frame_total = 0.
    with torch.no_grad():
        for batch_idx, (inputs, targets) in enumerate(testloader):
            
            inputs = Variable(inputs).to(device).half()
            targets = Variable(targets).to(device)
            
            tic = time.time()
            outputs = half_net(inputs)
            toc = time.time()
            
            if batch_idx != 0:
                FP16_time.append(toc-tic)
                avg_frame_total += (FP16_time[-1])
                avg_frame = avg_frame_total/batch_idx
                avg_frame = 1/avg_frame
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()
            
            if ((batch_idx != 0)and(batch_idx%2000==0))or batch_idx==9999:
                print(batch_idx, len(testloader), 'Acc: %.4f%% (%d/%d),FP16 Speed is : (%.3f [FPS])'
                % (100.*correct/total, correct, total, avg_frame))
'''
TensorRT_time = []
def TensorRT(epoch):
	# make_sample_image
	sample_img = np.random.rand(args.trtbatch,args.trtchannels,args.trtpixels,args.trtpixels)
	if args.trtFP == 32:
		# dummy_input FP 32
		input = torch.from_numpy(sample_img).view(args.trtbatch,args.trtchannels,args.trtpixels,args.trtpixels).float().to(device)
		tensorrt_net = args.network
		tensorrt_net.load_state_dict(torch.load(args.weight_path))
		tensorrt_net.float().to(device)
		# convert trt model FP 32
		net_trt = torch2trt(tensorrt_net,[input],fp16_mode = False,max_batch_size = args.trtbatch)
		net_trt.to(device)

	elif args.trtFP == 16:
		# dummy_input FP 16
		input =  torch.from_numpy(sample_img).view(args.trtbatch,args.trtchannels,args.trtpixels,args.trtpixels).half().to(device)
		tensorrt_net = args.network
		tensorrt_net.load_state_dict(torch.load(args.weight_path))
		tensorrt_net.half().to(device)
		# convert trt model FP 16
		net_trt = torch2trt(tensorrt_net,[input],fp16_mode = True,max_batch_size=args.trtbatch)
		net_trt.to(device)

	elif args.trtFP == 8:
		# dummy_input INT 8
		input = torch.from_numpy(sample_img).view(args.trtbatch,args.trtchannels,args.trtpixels,args.trtpixels).char().to(device)
		tensorrt_net = args.network
		tensorrt_net.load_state_dict(torch.load(args.weight_path))
		tensorrt_net.to(device)
		#convert trt model INT 8
		net_trt = torch2trt(tensorrt_net,[input],fp16_mode = False,int8_mode = True,max_batch_size = args.trtbatch)
		net_trt.to(device)
	print(input.dtype)
	print('=========Start_TensorRT_Check==========')
	net_trt.eval()
	correct = 0
	total = 0
	avg_frame_total = 0.
	with torch.no_grad():
		for batch_idx, (inputs, targets) in enumerate(testloader):
			# convert inputs dtype 
			if args.trtFP == 32:
				inputs = Variable(inputs).to(device)
			elif args.trtFP == 16:
				inputs = Variable(inputs).half().to(device)
			elif args.trtFP == 8:
				inputs = Variable(inputs).char().to(device)
			targets = Variable(targets).to(device) 
  
	    tic = time.time()
            outputs = net_trt(inputs)
            toc = time.time()
            
            if batch_idx != 0:
                TensorRT_time.append(toc-tic)
                avg_frame_total += (TensorRT_time[-1])
                avg_frame = avg_frame_total/batch_idx
                avg_frame = 1/avg_frame
            _, predicted = outputs.max(1)
            total += targets.size(0)
            correct += predicted.eq(targets).sum().item()
            
            if ((batch_idx != 0)and(batch_idx%2000==0))or batch_idx==9999:
                print(batch_idx, len(testloader), 'Acc: %.4f%% (%d/%d),TRT Speed is : (%.3f [FPS])'
                % (100.*correct/total, correct, total, avg_frame))
'''
for epoch in range(1):
    FP32(epoch)
    FP16(epoch)
    TensorRT(epoch)
