#! /usr/bin/python
# -*- coding: utf-8 -*-

import tensorflow as tf

from tensorlayer.layers.core import Layer

from tensorlayer.layers.utils.quantization import cabs
from tensorlayer.layers.utils.quantization import quantize_active
from tensorlayer.layers.utils.quantization import quantize_weight

from tensorlayer import logging

from tensorlayer.decorators import auto_parse_inputs
from tensorlayer.decorators import deprecated_alias
from tensorlayer.decorators import deprecated_args

__all__ = [
    'DorefaDenseLayer',
]


class DorefaDenseLayer(Layer):
    """The :class:`DorefaDenseLayer` class is a binary fully connected layer, which weights are 'bitW' bits and the output of the previous layer
    are 'bitA' bits while inferencing.

    Note that, the bias vector would not be binarized.

    Parameters
    ----------
    bitW : int
        The bits of this layer's parameter
    bitA : int
        The bits of the output of previous layer
    n_units : int
        The number of units of this layer.
    act : activation function
        The activation function of this layer, usually set to ``tf.act.sign`` or apply :class:`SignLayer` after :class:`BatchNormLayer`.
    gemmlowp_at_inference : boolean
        If True, use gemmlowp instead of ``tf.matmul`` (gemm) for inference. (TODO).
    W_init : initializer
        The initializer for the weight matrix.
    b_init : initializer or None
        The initializer for the bias vector. If None, skip biases.
    W_init_args : dictionary
        The arguments for the weight matrix initializer.
    b_init_args : dictionary
        The arguments for the bias vector initializer.
    name : a str
        A unique layer name.

    """

    def __init__(
        self,
        bitW=1,
        bitA=3,
        n_units=100,
        act=None,
        gemmlowp_at_inference=False,
        W_init=tf.truncated_normal_initializer(stddev=0.1),
        b_init=tf.constant_initializer(value=0.0),
        W_init_args=None,
        b_init_args=None,
        name='dorefa_dense',
    ):
        self.bitW = bitW
        self.bitA = bitA
        self.n_units = n_units
        self.act = act
        self.gemmlowp_at_inference = gemmlowp_at_inference
        self.W_init = W_init
        self.b_init = b_init
        self.W_init_args = W_init_args
        self.b_init_args = b_init_args
        self.name = name

        super(DorefaDenseLayer, self).__init__(W_init_args=W_init_args, b_init_args=b_init_args)

    def __str__(self):
        additional_str = []

        try:
            additional_str.append("n_units: %d" % self.n_units)
        except AttributeError:
            pass
        try:
            additional_str.append("bitW: %d" % self.bitW)
        except AttributeError:
            pass
        try:
            additional_str.append("bitA: %d" % self.bitA)
        except AttributeError:
            pass
        try:
            additional_str.append("act: %s" % self.act.__name__ if self.act is not None else 'No Activation')
        except AttributeError:
            pass

        try:
            additional_str.append("output shape: %s" % self._temp_data['outputs'].shape)
        except AttributeError:
            pass

        return self._str(additional_str)

    @auto_parse_inputs
    def compile(self, prev_layer, is_train=True):

        if self._temp_data['inputs'].get_shape().ndims != 2:
            raise Exception("The input dimension must be rank 2, please reshape or flatten it")

        if self.gemmlowp_at_inference:
            raise NotImplementedError("TODO. The current version use tf.matmul for inferencing.")

        n_in = int(self._temp_data['inputs'].get_shape()[-1])

        self._temp_data['inputs'] = quantize_active(cabs(self._temp_data['inputs']), self.bitA)

        with tf.variable_scope(self.name):

            weight_matrix = self._get_tf_variable(
                name='W',
                shape=(n_in, self.n_units),
                initializer=self.W_init,
                dtype=self._temp_data['inputs'].dtype,
                **self.W_init_args
            )
            # weight_matrix = tl.act.sign(weight_matrix)    # dont update ...
            weight_matrix = quantize_weight(weight_matrix, self.bitW)
            # weight_matrix = tf.Variable(weight_matrix)
            # print(weight_matrix)

            self._temp_data['outputs'] = tf.matmul(self._temp_data['inputs'], weight_matrix)
            # self._temp_data['outputs'] = xnor_gemm(self._temp_data['inputs'], weight_matrix) # TODO

            if self.b_init:
                try:
                    b = self._get_tf_variable(
                        name='b',
                        shape=(self.n_units),
                        initializer=self.b_init,
                        dtype=self._temp_data['inputs'].dtype,
                        **self.b_init_args
                    )

                except Exception:  # If initializer is a constant, do not specify shape.
                    b = self._get_tf_variable(
                        name='b', initializer=self.b_init, dtype=self._temp_data['inputs'].dtype, **self.b_init_args
                    )

                self._temp_data['outputs'] = tf.nn.bias_add(self._temp_data['outputs'], b, name='bias_add')
                # self._temp_data['outputs'] = xnor_gemm(self._temp_data['inputs'], weight_matrix) + b # TODO

            self._temp_data['outputs'] = self._apply_activation(self._temp_data['outputs'])
