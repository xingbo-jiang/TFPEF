import torch
import torch.nn as nn


def conv1x1(in_channels, out_channels, stride=1):
    return nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride, padding=0, bias=True)


def conv3x3(in_channels, out_channels, stride=1):
    return nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=True)


def conv5x5(in_channels, out_channels, stride=1):
    return nn.Conv2d(in_channels, out_channels, kernel_size=5, stride=stride, padding=2, bias=True)


def actFunc(act, *args, **kwargs):
    act = act.lower()
    if act == 'relu':
        return nn.ReLU()
    elif act == 'relu6':
        return nn.ReLU6()
    elif act == 'leakyrelu':
        return nn.LeakyReLU(0.1)
    elif act == 'prelu':
        return nn.PReLU()
    elif act == 'rrelu':
        return nn.RReLU(0.1, 0.3)
    elif act == 'selu':
        return nn.SELU()
    elif act == 'celu':
        return nn.CELU()
    elif act == 'elu':
        return nn.ELU()
    elif act == 'gelu':
        return nn.GELU()
    elif act == 'tanh':
        return nn.Tanh()
    else:
        raise NotImplementedError


class views_attention(nn.Module):
    # (5,c,h,w)->(5c,h,w)->(5,c,h,w)
    def __init__(self, n_features):
        super().__init__()
        self.pool_h = nn.AdaptiveAvgPool2d((None, 1))
        self.pool_w = nn.AdaptiveAvgPool2d((1, None))
        self.conv1 = nn.Conv2d(5 * n_features, 10 * n_features, kernel_size=1, stride=1, padding=0)
        self.ln1 = nn.LayerNorm([50,1])# (H+W)
        self.ln2 = nn.LayerNorm([20,30])
        self.act = nn.LeakyReLU()

        self.conv_h = nn.Conv2d(10 * n_features, 5 * n_features, kernel_size=1, stride=1, padding=0)
        self.conv_w = nn.Conv2d(10 * n_features, 5 * n_features, kernel_size=1, stride=1, padding=0)

        self.conv_c = nn.Conv2d(5 * n_features, 10 * n_features, kernel_size=1, stride=1, padding=0)
        self.conv_c2 = nn.Conv2d(10 * n_features, 5 * n_features, kernel_size=1, stride=1, padding=0)

    def forward(self, x):
        views, channels, h, w = x.shape

        x_ = x.reshape(-1, h, w)
        x_h = self.pool_h(x_)
        x_w = self.pool_w(x_).permute(0, 2, 1)
        x_spatial = torch.cat([x_h, x_w], dim=1)  # (c,h+w,1)
        x_spatial = self.conv1(x_spatial)
        x_spatial = self.ln1(x_spatial)
        x_spatial = self.act(x_spatial)
        x_h, x_w = torch.split(x_spatial, [h, w], dim=1)
        x_w = x_w.permute(0, 2, 1)
        a_h = self.conv_h(x_h).sigmoid()
        a_w = self.conv_h(x_w).sigmoid()

        x_c = self.conv_c(x_)
        x_c = self.ln2(x_c)
        x_c = self.act(x_c)
        a_c = self.conv_c2(x_c).sigmoid()

        x_ = x_ * a_w * a_h * a_c
        x_ = x_.reshape(views, channels, h, w)
        out = x + x_
        return out


# dense layer
class dense_layer(nn.Module):
    def __init__(self, in_channels, growthRate, activation='leakyrelu'):
        super(dense_layer, self).__init__()
        self.conv = conv3x3(in_channels, growthRate)
        self.act = actFunc(activation)

    def forward(self, x):
        out = self.act(self.conv(x))
        out = torch.cat((x, out), 1)
        return out


# Residuel dense block
class RDB(nn.Module):
    def __init__(self, in_channels, growthRate, num_layer, activation='leakyrelu'):
        super(RDB, self).__init__()
        in_channels_ = in_channels
        modules = []
        for i in range(num_layer):
            modules.append(dense_layer(in_channels_, growthRate, activation))
            in_channels_ += growthRate
        self.dense_layers = nn.Sequential(*modules)
        self.conv1x1 = conv1x1(in_channels_, in_channels)

    def forward(self, x):
        out = self.dense_layers(x)
        out = self.conv1x1(out)
        out += x
        return out


# Middle network of residual dense blocks
class RDNet(nn.Module):
    def __init__(self, in_channels, growthRate, num_layer, num_blocks, activation='leakyrelu'):
        super(RDNet, self).__init__()
        self.num_blocks = num_blocks
        self.RDBs = nn.ModuleList()
        for i in range(num_blocks):
            self.RDBs.append(RDB(in_channels, growthRate, num_layer, activation))
        self.conv1x1 = conv1x1(num_blocks * in_channels, in_channels)
        self.conv3x3 = conv3x3(in_channels, in_channels)

    def forward(self, x):
        out = []
        h = x
        for i in range(self.num_blocks):
            h = self.RDBs[i](h)
            out.append(h)
        out = torch.cat(out, dim=1)
        out = self.conv1x1(out)
        out = self.conv3x3(out)
        return out


class RDNet_cn2(nn.Module):
    def __init__(self, in_channels, out_channels, growthRate, num_layer, num_blocks, activation='leakyrelu'):
        super(RDNet_cn2, self).__init__()
        self.num_blocks = num_blocks
        self.RDBs = nn.ModuleList()
        for i in range(num_blocks):
            self.RDBs.append(RDB(in_channels, growthRate, num_layer, activation))
        self.conv1x1 = conv1x1(num_blocks * in_channels, out_channels)
        self.conv3x3 = conv3x3(out_channels, out_channels)

    def forward(self, x):
        out = []
        h = x
        for i in range(self.num_blocks):
            h = self.RDBs[i](h)
            out.append(h)
        out = torch.cat(out, dim=1)
        out = self.conv1x1(out)
        out = self.conv3x3(out)
        return out


class RDB_DS(nn.Module):
    def __init__(self, in_channels, growthRate, num_layer, activation='leakyrelu'):
        super(RDB_DS, self).__init__()
        self.rdb = RDB(in_channels, growthRate, num_layer, activation)
        self.down_sampling = conv5x5(in_channels, 2 * in_channels, stride=2)

    def forward(self, x):
        x = self.rdb(x)
        out = self.down_sampling(x)

        return out


# RDB-based RNN cell
class RDBCell(nn.Module):
    def __init__(self, activation, n_features, n_blocks):
        super(RDBCell, self).__init__()
        self.activation = activation
        self.n_feats = n_features
        self.n_blocks = n_blocks

        self.F_B0 = conv5x5(3, self.n_feats, stride=1)
        # 降采样特征提取
        self.F_B1 = RDB_DS(in_channels=self.n_feats, growthRate=self.n_feats, num_layer=2, activation=self.activation)
        self.F_B2 = RDB_DS(in_channels=2 * self.n_feats, growthRate=int(self.n_feats * 1), num_layer=2,
                           activation=self.activation)
        self.F_B3 = RDB_DS(in_channels=4 * self.n_feats, growthRate=int(self.n_feats * 2), num_layer=2,
                           activation=self.activation)
        self.F_B4 = RDB_DS(in_channels=8 * self.n_feats, growthRate=int(self.n_feats * 4), num_layer=2,
                           activation=self.activation)
        # RDBs
        self.F_R = RDNet(in_channels=(1 + 16) * self.n_feats, growthRate=self.n_feats, num_layer=2,
                         num_blocks=2, activation=self.activation)  # in: 80
        # F_h: hidden state part
        # 卷积提取ht 残差  通道数为n
        self.F_h = nn.Sequential(
            RDNet(in_channels=(1 + 16) * self.n_feats, growthRate=self.n_feats, num_layer=2, num_blocks=2,
                  activation=self.activation),
            conv3x3((1 + 16) * self.n_feats, self.n_feats),
            RDB(in_channels=self.n_feats, growthRate=self.n_feats, num_layer=3, activation=self.activation),
            conv3x3(self.n_feats, self.n_feats)
        )
        self.view_att = views_attention(self.n_feats)

    def forward(self, x, s_last):
        out = self.F_B0(x)
        out = self.F_B1(out)
        out = self.F_B2(out)
        out = self.F_B3(out)
        out = self.F_B4(out)
        out = torch.cat([out, s_last], dim=1)
        s = self.F_h(out)  # (5,n_feats,h/16,w/16)
        s = self.view_att(s)
        # ->(5,n_feats,h,w)->(_,h,w)

        return s

class Linear(nn.Module):
    def __init__(self, size_w, size_h, n_features, size_out):
        super(Linear, self).__init__()
        self.linear = nn.Sequential(nn.Linear(n_features * size_h * size_w, size_out))

    def forward(self, x):
        # print('--------------------xsize')
        # print(x.shape)
        out = torch.flatten(x, start_dim=1)
        out = self.linear(out)
        return out

class reprojection(nn.Module):
    def __init__(self,  growthRate = 3, num_layer=3, num_blocks=6, activation='leakyrelu',channel_2d = 5,channel_3d = 30):
        super(reprojection, self).__init__()
        self.rdn_2dto3d = RDNet_cn2(in_channels=channel_2d, out_channels=channel_3d, growthRate = growthRate,num_layer = num_layer,num_blocks = num_blocks)
        self.rdn_3dto2d = RDNet_cn2(in_channels=channel_3d, out_channels=channel_2d, growthRate = growthRate,num_layer = num_layer,num_blocks = num_blocks)
    def forward(self, x):
        x_2d = x[:,:5,:,:]
        x_3d = x[:,5:,:,:]
        out_3d = self.rdn_2dto3d(x_2d)
        out_2d = self.rdn_3dto2d(x_3d)
        out = torch.cat([out_2d, out_3d], dim=1)
        return out


