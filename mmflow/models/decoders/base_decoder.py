# Copyright (c) OpenMMLab. All rights reserved.
from abc import abstractmethod
from typing import Optional, Sequence, Union

import torch.nn.functional as F
from mmengine.data import PixelData
from mmengine.model import BaseModule
from torch import Tensor

from mmflow.structures import FlowDataSample
from mmflow.utils import OptSampleList, SampleList, TensorDict


class BaseDecoder(BaseModule):
    """Base class for decoder.

    Args:
        init_cfg (dict, list, optional): Config dict of weights initialization.
            Default: None.
    """

    def __init__(self, init_cfg: Optional[Union[dict, list]] = None) -> None:

        super().__init__(init_cfg=init_cfg)

    @abstractmethod
    def forward(self, *args, **kwargs):
        """Placeholder of forward function."""
        pass

    @abstractmethod
    def loss(self, *args, **kwargs):
        """Placeholder of forward function when model training."""
        pass

    @abstractmethod
    def predict(self, *args, **kwargs):
        """Placeholder of forward function when model testing."""
        pass

    @abstractmethod
    def loss_by_feat(self, *args, **kwargs) -> TensorDict:
        """Placeholder for model computing losses."""
        pass

    def postprocess_result(
            self,
            flow_results: Tensor,
            data_samples: OptSampleList = None) -> Sequence[FlowDataSample]:
        """Reverted flow as original size of ground truth.

        Args:
            flow_results (Tensor): predicted results of optical flow.
            data_samples (list[:obj:`FlowDataSample`], optional): The
                annotation data of every samples. Defaults to None.

        Returns:
            Sequence[FlowDataSample]: the reverted predicted optical flow.
        """
        # unravel batch dim,
        flow_results = list(flow_results)
        # results = [dict(flow_fw=f) for f in flow_results]

        only_prediction = False
        if data_samples is None:
            data_samples = []
            only_prediction = True
        else:
            assert len(flow_results) == len(data_samples)

        for i in range(len(flow_results)):
            if only_prediction:
                prediction = FlowDataSample()
                prediction.set_data(
                    {'pred_flow_fw': PixelData(**{'data': flow_results[i]})})
                data_samples.append(prediction)
            else:
                img_meta = data_samples[i].metainfo
                ori_H, ori_W = img_meta['ori_shape']
                pad = img_meta.get('pad', None)
                w_scale, h_scale = img_meta.get('scale_factor', (None, None))
                f = flow_results[i]
                if f is not None:
                    # shape is 2, H, W
                    H, W = f.shape[1:]
                    if pad is not None:
                        f = f[:, pad[0][0]:(H - pad[0][1]),
                              pad[1][0]:(W - pad[1][1])]

                    elif (w_scale is not None and h_scale is not None):
                        f = F.interpolate(
                            f[None],
                            size=(ori_H, ori_W),
                            mode='bilinear',
                            align_corners=False).squeeze(0)
                        f[0, :, :] = f[0, :, :] / w_scale
                        f[1, :, :] = f[1, :, :] / h_scale
                data_samples[i].set_data(
                    {'pred_flow_fw': PixelData(**{'data': f})})
            return data_samples

    def predict_by_feat(self,
                        flow_results: Tensor,
                        data_samples: OptSampleList = None) -> SampleList:
        """Predict list of obj:`FlowDataSample` from flow tensor.

        Args:
            flow_results (Tensor): Input flow tensor.
            data_samples (list[:obj:`FlowDataSample`], optional): The
                annotation data of every samples. Defaults to None.

        Returns:
            Sequence[FlowDataSample]: the reverted predicted optical flow.
        """
        if data_samples is None:
            flow_results = flow_results * self.flow_div
            return self.postprocess_result(flow_results, data_samples=None)

        H, W = data_samples[0].metainfo['img_shape'][:2]
        # resize flow to the size of images after augmentation.
        flow_results = F.interpolate(
            flow_results, size=(H, W), mode='bilinear', align_corners=False)

        flow_results = flow_results * self.flow_div

        return self.postprocess_result(flow_results, data_samples=data_samples)
