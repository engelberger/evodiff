FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-devel

# Set up environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV DGLBACKEND="pytorch"

# Update and install required packages
RUN apt-get update && apt-get install -y --no-install-recommends wget ca-certificates git build-essential curl unzip

# Install MicroMamba
RUN cd /tmp && curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xvj bin/micromamba

RUN /tmp/bin/micromamba create -y -n evodiff -c nvidia -c pyg -c pytorch -c conda-forge python=3.8.5  pytorch-cuda=11.7 pytorch==2.0.1 pyg
RUN /root/micromamba/envs/evodiff/bin/python3.8 -m pip install evodiff ipykernel
#RUN /root/micromamba/envs/evodiff/bin/python3.8 -m pip install torch-scatter torchvision torchaudio 

