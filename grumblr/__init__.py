
import gevent.monkey
gevent.monkey.patch_all()
from gevent.pool import Pool

import os
import json
import time
import argparse
from os.path import expanduser

import yaml
import pytumblr
from boltons.dictutils import OMD
from boltons.osutils import mkdir_p
from progressbar import ProgressBar, Bar, Percentage, SimpleProgress


DEFAULT_CONCURRENCY = 20

# arg parse
# - concurrency
# - target blog
# - config location

DEFAULT_HOME_PATH = '~/.grumblr/'

# TODO: loggiiiiing
# TODO: resumability of fetch + use boltons.atomic_save


class Grumblog(object):
    def __init__(self, blog_name, posts, last_modified, last_fetched,
                 path=None):
        self.path = path
        self.blog_name = blog_name
        self.last_modified = last_modified
        self.last_fetched = last_fetched
        self.posts = posts
        self.changes = []

    @property
    def blog_domain(self):
        if '.' in self.blog_name:
            return self.blog_name
        else:
            return '%s.tumblr.com' % self.blog_name

    @classmethod
    def from_dict(cls, blog_dict):
        bd = blog_dict
        return cls(blog_name=bd['blog_name'],
                   posts=bd['posts'],
                   last_modified=bd['last_modified'],
                   last_fetched=bd['last_fetched'],
                   path=bd.get('path'))

    @classmethod
    def from_path(cls, path):
        with open(path) as f:
            ret = cls.from_dict(json.load(f))
        ret.path = path
        return ret

    def save(self, path=None):
        if not self.path and not path:
            raise ValueError('no path set')
        self.path = path or self.path
        with open(self.path, 'w') as f:
            to_write = {'last_modified': self.last_modified,
                        'last_fetched': self.last_fetched,
                        'blog_name': self.blog_name,
                        'posts': self.posts}
            json.dump(to_write, f)
        return

    def get_tag_posts_map(self):
        tpm = OMD()
        for post_id, post in self.posts.iteritems():
            for tag in post['tags']:
                tpm.add(tag, post)
        # pop_tags = sorted(tpm.counts().items(), key=lambda x: x[1],
        #                   reverse=True)
        return tpm

    def get_nonlower_tag_map(self):
        nltm = OMD()
        for pid, post in self.posts.iteritems():
            for tag in post['tags']:
                if tag.lower() != tag:
                    nltm.add(tag, post)
        return nltm

    def get_untagged_posts(self):
        return OMD([(pid, post) for pid, post in self.posts.iteritems()
                    if not post['tags']])

    def get_report_dict(self):
        # TODO: first post date?
        posts = self.posts
        ret = {'blog_name': self.blog_name,
               'blog_domain': self.blog_domain,
               'last_fetched': self.last_fetched,
               'post_count': len(posts)}
        tpm = self.get_tag_posts_map()
        ret['tag_count'] = len(tpm)
        ret['tag_count_map'] = OMD(sorted(tpm.counts().items(),
                                          key=lambda x: x[1],
                                          reverse=True))
        tag_rate = 1.0 - (1.0 * len(self.get_untagged_posts()) / len(posts))
        ret['tag_percent'] = round(100.0 * tag_rate, 2)
        tag_post_ratio = float(sum(tpm.counts().values())) / len(posts)
        ret['tag_post_ratio'] = round(tag_post_ratio, 2)

        return ret


class Grumblr(object):

    _blog_type = Grumblog

    def __init__(self, home_path=DEFAULT_HOME_PATH, **kwargs):
        self.default_blog_name = kwargs.pop('blog_name', None)
        self.default_action = kwargs.pop('action', None)

        self.concurrency = kwargs.pop('concurrency', DEFAULT_CONCURRENCY)

        self.home_path = expanduser(home_path)
        default_config_path = self.home_path + 'config.yaml'
        self.config_path = expanduser(kwargs.pop('config_path',
                                                 default_config_path))
        if kwargs:
            raise TypeError('unexpected keyword arguments: %r' % kwargs.keys())

        if not os.path.exists(self.home_path):
            mkdir_p(self.home_path)
        if not os.path.isfile(self.config_path):
            # write default config file
            raise RuntimeError('please create config file at %r'
                               % self.config_path)
        with open(self.config_path) as f:
            self.config = config = yaml.load(f.read())

        self.blogs_path = self.home_path + 'blogs/'
        if not os.path.exists(self.blogs_path):
            mkdir_p(self.blogs_path)

        self.client = pytumblr.TumblrRestClient(config['consumer_key'],
                                                config['consumer_secret'],
                                                config['oauth_token'],
                                                config['oauth_secret'])

    def load_blog(self, blog_name):
        blog_type = self._blog_type
        return blog_type.from_path('%s%s.json' % (self.blogs_path, blog_name))

    def _fetch_update_blog(self, blog_name):
        # TODO
        # load posts
        # find most recent post id
        # fetch until that id is found
        # add posts to the blog
        # resave
        pass

    def fetch_blog(self, blog_name):
        posts = OMD()
        step = 20
        client = self.client
        pool = Pool(self.concurrency)

        resp = client.posts(blog_name, limit=20, filter='raw')
        posts.update([(p['id'], p) for p in resp['posts']])

        total_posts = resp['total_posts']  # for the progress bar
        pb = ProgressBar(
            widgets=[Percentage(),
                     ' ', Bar(),
                     ' ', SimpleProgress()],
            maxval=total_posts + 1).start()
        pb.update(len(posts))

        def _get_posts(offset):
            return client.posts(blog_name, offset=offset, limit=step,
                                filter='raw')

        for resp in pool.imap_unordered(_get_posts,
                                        range(20, total_posts, step)):
            cur_posts = resp['posts']
            posts.update([(p['id'], p) for p in cur_posts])
            pb.update(len(posts))

        pool.join(timeout=0.3, raise_error=True)
        print 'Done, saving', len(posts), 'posts.'

        save_path = self.blogs_path + '%s.json' % blog_name
        fetched_blog = Grumblog(blog_name=blog_name,
                                posts=posts,
                                last_modified=time.time(),
                                last_fetched=time.time(),
                                path=save_path)
        fetched_blog.save()
        return

    @classmethod
    def get_argparser(cls):
        prs = argparse.ArgumentParser()
        subprs = prs.add_subparsers(dest='action',
                                    help='grumblr supports fetch and report'
                                    ' subcommands')
        subprs.add_parser('fetch',
                          help='fetch and save a local version of a blog')
        subprs.add_parser('report',
                          help='generate a report about a blog')

        add_arg = prs.add_argument
        add_arg('--home', default=DEFAULT_HOME_PATH,
                help='grumblr home path, with cached blogs, config, etc.'
                'defaults to ~/.grumblr')
        add_arg('--conc', default=DEFAULT_CONCURRENCY,
                help='number of concurrent requests to allow during fetches')
        add_arg('blog_name', help='the target blog')
        return prs

    @classmethod
    def from_args(cls):
        kwarg_map = {'conc': 'concurrency',
                     'home': 'home_path'}
        prs = cls.get_argparser()
        kwargs = dict(prs.parse_args()._get_kwargs())
        for src, dest in kwarg_map.items():
            kwargs[dest] = kwargs.pop(src)
        return cls(**kwargs)


def coalesce_tag(blog_name, posts, client, src_tag, dest_tag):
    assert dest_tag and dest_tag != src_tag

    todo = []
    for post_id, post in posts.iteritems():
        if src_tag in post['tags']:
            todo.append(post)
    if not todo:
        return
    for post in todo:
        cur_tags = post['tags']
        src_i = cur_tags.index(src_tag)
        new_tags = cur_tags[:src_i] + [dest_tag] + cur_tags[src_i + 1:]
        resp = client.edit_post(blog_name, id=post['id'], tags=new_tags)
        # if it was successful, write back to the cached version?
        import pdb;pdb.set_trace()


def _proc_untagged(posts):
    untagged = OMD(sorted([p for p in posts.iteritems() if not p[1]['tags']],
                          key=lambda p: p[1]['timestamp']))
    for i, p in enumerate(untagged.values()):
        print i, '-', 'http://tumblr.com/edit/%s' % p['id']


# TODO: sort tags by length, check on necessity of longest and shortest

if __name__ == '__main__':
    main()
