import tensorflow as tf
import numpy as np
import os
import re
import json
from itertools import chain

from bayou.core.utils import CONFIG_ENCODER, C0, UNK, split_camel
from bayou.lda.model import LDA


class Evidence(object):

    def init_config(self, evidence, save_dir):
        for attr in CONFIG_ENCODER:
            self.__setattr__(attr, evidence[attr])
        self.load_embedding(save_dir)

    def dump_config(self):
        js = {attr: self.__getattribute__(attr) for attr in CONFIG_ENCODER}
        return js

    @staticmethod
    def read_config(js, save_dir):
        evidences = []
        for evidence in js:
            name = evidence['name']
            if name == 'keywords':
                e = Keywords()
            elif name == 'types':
                e = Types()
            elif name == 'context':
                e = Context()
            else:
                raise TypeError('Invalid evidence name: {}'.format(name))
            e.init_config(evidence, save_dir)
            evidences.append(e)
        return evidences

    def load_embedding(self, save_dir):
        raise NotImplementedError('load_embedding() has not been implemented')

    def read_data_point(self, program):
        raise NotImplementedError('read_data() has not been implemented')

    def wrangle(self, data):
        raise NotImplementedError('wrangle() has not been implemented')

    def placeholder(self, config):
        raise NotImplementedError('placeholder() has not been implemented')

    def encode(self, inputs, config):
        raise NotImplementedError('encode() has not been implemented')


class Keywords(Evidence):

    def load_embedding(self, save_dir):
        embed_save_dir = os.path.join(save_dir, 'embed_keywords')
        self.lda = LDA(from_file=os.path.join(embed_save_dir, 'model.pkl'))

    def read_data_point(self, program):
        keywords = program['keywords'] if 'keywords' in program else []
        keywords = list(set(keywords))
        return keywords

    def wrangle(self, data):
        return np.array(self.lda.infer(data), dtype=np.float32)

    def placeholder(self, config):
        return tf.placeholder(tf.float32, [config.batch_size, self.lda.model.n_topics])

    def encode(self, inputs, config):
        with tf.variable_scope('keywords'):
            encoding = tf.layers.dense(inputs, self.units)
            w = tf.get_variable('w', [self.units, config.latent_size])
            b = tf.get_variable('b', [config.latent_size])
            latent_encoding = tf.nn.xw_plus_b(encoding, w, b)
            return [latent_encoding] * self.tile

    @staticmethod
    def from_call(call):
        split = call.split('(')[0].split('.')
        cls, name = split[-2:]
        return split_camel(name) if not cls == name else []


class Types(Evidence):

    def load_embedding(self, save_dir):
        embed_save_dir = os.path.join(save_dir, 'embed_types')
        self.lda = LDA(from_file=os.path.join(embed_save_dir, 'model.pkl'))

    def read_data_point(self, program):
        types = program['types'] if 'types' in program else []
        types = list(set(types))
        return types

    def wrangle(self, data):
        return np.array(self.lda.infer(data), dtype=np.float32)

    def placeholder(self, config):
        return tf.placeholder(tf.float32, [config.batch_size, self.lda.model.n_topics])

    def encode(self, inputs, config):
        with tf.variable_scope('types'):
            encoding = tf.layers.dense(inputs, self.units)
            w = tf.get_variable('w', [self.units, config.latent_size])
            b = tf.get_variable('b', [config.latent_size])
            latent_encoding = tf.nn.xw_plus_b(encoding, w, b)
            return [latent_encoding] * self.tile

    @staticmethod
    def from_call(call):
        split = list(reversed([q for q in call.split('(')[0].split('.')[:-1]
                               if q[0].isupper()]))
        inner = split_camel(split[0])
        outer = split_camel(split[1]) if len(split) > 1 else []
        return inner + outer


class Context(Evidence):

    def load_embedding(self, save_dir):
        embed_save_dir = os.path.join(save_dir, 'embed_context')
        self.lda = LDA(from_file=os.path.join(embed_save_dir, 'model.pkl'))

    def read_data_point(self, program):
        context = program['context'] if 'context' in program else []
        context = list(set(context))
        return context

    def wrangle(self, data):
        return np.array(self.lda.infer(data), dtype=np.float32)

    def placeholder(self, config):
        return tf.placeholder(tf.float32, [config.batch_size, self.lda.model.n_topics])

    def encode(self, inputs, config):
        with tf.variable_scope('context'):
            encoding = tf.layers.dense(inputs, self.units)
            w = tf.get_variable('w', [self.units, config.latent_size])
            b = tf.get_variable('b', [config.latent_size])
            latent_encoding = tf.nn.xw_plus_b(encoding, w, b)
            return [latent_encoding] * self.tile

    @staticmethod
    def from_call(call):
        args = call.split('(')[1].split(')')[0].split(',')
        args = [arg.split('.')[-1] for arg in args]
        args = [re.sub('<.*', r'', arg) for arg in args]  # remove generics
        args = [re.sub('\[\]', r'', arg) for arg in args]  # remove array type
        contexts = list(chain.from_iterable([split_camel(arg) for arg in args]))
        return [c for c in contexts if not c == '']


# TODO: handle Javadoc with word2vec
class Javadoc(Evidence):

    def read_data_point(self, program, infer=False):
        javadoc = program['javadoc'] if 'javadoc' in program else None
        if not javadoc:
            javadoc = UNK
        try:  # do not consider non-ASCII javadoc
            javadoc.encode('ascii')
        except UnicodeEncodeError:
            javadoc = UNK
        javadoc = javadoc.split()
        return javadoc

    def set_dicts(self, data):
        if self.pretrained_embed:
            save_dir = os.path.join(self.save_dir, 'embed_' + self.name)
            with open(os.path.join(save_dir, 'config.json')) as f:
                js = json.load(f)
            self.chars = js['chars']
        else:
            self.chars = [C0] + list(set([w for point in data for w in point]))
        self.vocab = dict(zip(self.chars, range(len(self.chars))))
        self.vocab_size = len(self.vocab)


