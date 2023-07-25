import numpy as np
from evodiff.pretrained import CARP_38M, CARP_640M, D3PM_BLOSUM_38M, D3PM_BLOSUM_640M, D3PM_UNIFORM_38M, D3PM_UNIFORM_640M,\
                           OA_AR_640M, OA_AR_38M, LR_AR_38M, LR_AR_640M, ESM1b_650M
from torch.nn import CrossEntropyLoss
from evodiff.losses import OAMaskedCrossEntropyLoss
from sequence_models.losses import MaskedCrossEntropyLoss
import torch
from sequence_models.datasets import UniRefDataset
from tqdm import tqdm
import pandas as pd
from evodiff.plot import plot_perp_group_masked, plot_perp_group_d3pm
import argparse

def main():
    # set seeds
    _ = torch.manual_seed(0)
    np.random.seed(0)

    parser = argparse.ArgumentParser()
    parser.add_argument('--model-type', type=str, default='D3PM_BLOSUM_38M',
                        help='Choice of: carp_38M carp_640M esm1b_640M \
                              oa_ar_38M oa_ar_640M \
                              lr_ar_38M lr_ar_640M \
                              d3pm_blosum_38M d3pm_blosum_640M \
                              d3pm_uniform_38M d3pm_uniform_38M')
    args = parser.parse_args()

    save_name = args.model_type

    if args.model_type=='esm1b_650M':
        checkpoint = ESM1b_650M()
    elif args.model_type=='carp_38M':
        checkpoint = CARP_38M()
    elif args.model_type=='carp_640M':
        checkpoint = CARP_640M()
    elif args.model_type=='oa_ar_38M':
        checkpoint = OA_AR_38M()
    elif args.model_type=='oa_ar_640M':
        checkpoint = OA_AR_640M()
    elif args.model_type=='lr_ar_38M':
        checkpoint = LR_AR_38M()
    elif args.model_type=='lr_ar_640M':
        checkpoint = LR_AR_640M()
    elif args.model_type=='d3pm_blosum_38M':
        checkpoint = D3PM_BLOSUM_38M()
    elif args.model_type=='d3pm_blosum_640M':
        checkpoint = D3PM_BLOSUM_640M()
    elif args.model_type == 'd3pm_uniform_38M':
        checkpoint = D3PM_UNIFORM_38M()
    elif args.model_type == 'd3pm_uniform_640M':
        checkpoint = D3PM_UNIFORM_640M()
    else:
        print("Please select valid model")

    if save_name=='esm1b_650M':
        max_len=1022 # For ESM max_len=1022 + start/stop tokens
    else:
        max_len=2048

    # Def read seqs from fasta
    data = UniRefDataset('data/uniref50/', 'rtest', structure=False, max_len=max_len)

    losses = []
    n_tokens = []
    time_loss_data = []
    for i in tqdm(range(60000)): #len(data))):
        r_idx = np.random.choice(len(data))
        sequence = [data[r_idx]]
        t, loss, tokens = sum_nll_mask(sequence, checkpoint)
        if len(loss) > 0:
            for j in range(len(loss)):
                if not np.isnan(loss[j]):  # esm-1b predicts nans at large % mask
                    losses.append(loss[j].item())
                    n_tokens.append(tokens[j])
                    time_loss_data.append([t[j], loss[j], tokens[j]])
        else:
            if not np.isnan(loss): #esm-1b predicts nans at large % mask
                losses.append(loss)
                n_tokens.append(tokens)
                time_loss_data.append([t, loss, tokens])
        if i % 100 == 0:
            ll = -sum(losses) / sum(n_tokens)
            perp = np.exp(-ll)
            #print(i, "samples, perp:", np.mean(perp))
    print("Final test perp:", np.exp(sum(losses)/sum(n_tokens)))
    df = pd.DataFrame(time_loss_data, columns=['time', 'loss', 'tokens'])
    if checkpoint[-1] == 'd3pm':
        plot_perp_group_d3pm(df, save_name)
    else:
        plot_perp_group_masked(df, save_name, mask=checkpoint[-1])

def sum_nll_mask(sequence, checkpoint):
    model, collater, tokenizer, scheme = checkpoint
    model.eval().cuda() # Use model.eval() if using CPU

    # D3PM Collater returns; src, src_one_hot, timesteps, tokenized, tokenized_one_hot, Q, Q_bar, q_x
    if scheme == 'd3pm':
        src, src_onehot, timestep, tgt, tgt_onehot, Q, Q_bar, q = collater(sequence)
    elif scheme == 'mask' or scheme=='causal-mask':
        if scheme == 'mask':
            src, timestep, tgt, mask = collater(sequence)
        elif scheme == 'causal-mask':
            src, tgt, mask = collater(sequence)
        timestep = torch.tensor([0] * len(src))  # placeholder in model
        input_mask = (src != tokenizer.pad_id).float() # placeholder, should be no pads since not batching
        mask = mask.cuda()
        input_mask = input_mask.cuda()
    elif scheme == 'esm-mask':
        src, timestep, tgt, mask = collater(sequence)
        input_mask = (src != tokenizer.padding_idx).float()  # placeholder, should be no pads since not batching
        mask = mask.cuda()
        input_mask = input_mask.cuda()
    src = src.cuda()     # Comment all variable.cuda() lines if using CPU
    timestep = timestep.cuda()
    tgt = tgt.cuda()
    with torch.no_grad():
        #print(timestep)
        outputs = model(src, timestep) # outputs are x_tilde_0 (predicted tgt)
        if scheme == 'esm-mask':
            outputs = outputs["logits"]

    # Get loss (NLL ~= CE)
    if scheme == 'd3pm':
        loss_func = CrossEntropyLoss(reduction='sum')
        nll_loss = loss_func(outputs.squeeze(), tgt.squeeze())
        nll_loss = nll_loss.item()
        t_out=timestep
        tokens = len(tgt.squeeze())
    elif scheme == 'mask' or scheme == 'esm-mask' or scheme=='causal-mask':
        if scheme=='causal-mask': # LR-AR only predict next token
            loss_func = MaskedCrossEntropyLoss(reduction='none')
            n_tokens = mask.sum().item()
            nll_loss = loss_func(outputs, tgt, mask)
            # For each token in loss, append sum of loss up to N tokens, and N tokens
            nll_loss = nll_loss.cpu()
            nll_loss = [nll_loss[:i].sum() for i in range(n_tokens)]
            tokens = [(i+1) for i in range(n_tokens)]
            t_out = [(i+1)/n_tokens for i in range(n_tokens)]
        else:
            loss_func = OAMaskedCrossEntropyLoss(reweight=False)
            ce_loss, nll_loss = loss_func(outputs[:, :, :26], tgt, mask, timestep, input_mask) # returns a sum
            nll_loss = nll_loss.item()
            tokens = mask.sum().item()
            t_out = tokens / int(len(tgt.squeeze()))
    return t_out, nll_loss, tokens # return timestep sampled (or % masked), sum of losses, and sum of tokens

if __name__ == '__main__':
    main()