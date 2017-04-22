
import gevent.monkey
gevent.monkey.patch_all()
from gevent.pool import Pool

import os
import sys
import json
import time
import argparse
from os.path import expanduser

import yaml
import pytumblr
from boltons.dictutils import OMD
from boltons.fileutils import mkdir_p
from boltons.setutils import IndexedSet
from boltons.strutils import pluralize
from progressbar import ProgressBar, Bar, Percentage, SimpleProgress


DEFAULT_CONCURRENCY = 2

# TODO: on report generation, if there's just one post under a tag, link directly to the post.


def print_dot():
    sys.stdout.write('.')
    sys.stdout.flush()


def get_user_confirmation(question, default="yes"):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is True:
        default = 'y'
    elif default is False:
        default = 'n'

    if default is None:
        prompt = " [y/n] "
    elif valid.get(default.lower()) is True:
        prompt = " [Y/n] "
    elif valid.get(default.lower()) is False:
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            ret = valid[default]
            break
        elif choice in valid:
            ret = valid[choice]
            break
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")
    return ret


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

        self.concurrency = int(kwargs.pop('concurrency', DEFAULT_CONCURRENCY))

        self.home_path = expanduser(home_path)
        default_config_path = self.home_path + 'config.yaml'
        self.config_path = expanduser(kwargs.pop('config_path',
                                                 default_config_path))
        self.debug = kwargs.pop('debug', None)
        self.kwargs = kwargs

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

        errors = []
        for resp in pool.imap_unordered(_get_posts,
                                        range(20, total_posts, step)):
            try:
                cur_posts = resp['posts']
            except KeyError:
                # likely error (a lot of these started occurring after
                # tumblr was put behind yahoo load balancers/rate
                # limiters. they just return blank pages instead of
                # any real error)
                errors.append(resp)
                continue
            posts.update([(p['id'], p) for p in cur_posts])
            if len(posts) > pb.maxval:
                pb.maxval = len(posts)
            pb.update(len(posts))

        pool.join(timeout=0.3, raise_error=True)
        print 'Done, saving', len(posts), 'posts.'
        if errors:
            print 'Note: %s error(s) were encountered:' % len(errors)
            print '\n'.join(['    %r' % e for e in errors])

        save_path = self.blogs_path + '%s.json' % blog_name
        fetched_blog = Grumblog(blog_name=blog_name,
                                posts=posts,
                                last_modified=time.time(),
                                last_fetched=time.time(),
                                path=save_path)
        fetched_blog.save()
        return

    def coalesce_tags_to_lower(self, blog):
        to_proc = OMD()
        tpm = blog.get_tag_posts_map()
        for tag in tpm:
            lower_tag = tag.lower()
            if tag == lower_tag:
                continue
            if lower_tag in tpm:
                to_proc.add(lower_tag, tag)
        for lower_tag in to_proc:
            target_tags = to_proc.getlist(lower_tag) + [lower_tag]
            print 'coalescing', target_tags
            self.coalesce_tag(blog, target_tags)

    def coalesce_tags_to_plural(self, blog, confirm=True):
        to_proc = OMD()
        tpm = blog.get_tag_posts_map()
        for tag in tpm:
            plural_tag = pluralize(tag)
            if tag == plural_tag:
                continue
            if plural_tag in tpm:
                to_proc.add(plural_tag, tag)
        for plural_tag in to_proc:
            target_tags = to_proc.getlist(plural_tag) + [plural_tag]
            self.coalesce_tag(blog, target_tags, confirm=confirm)

    def coalesce_tag(self, blog, target_tags, confirm=False):
        target_tags = IndexedSet(target_tags)
        src_tags = target_tags[:-1]
        dest_tag = target_tags[-1]
        assert src_tags

        todo = []
        dest_count = 0
        for post_id, post in blog.posts.iteritems():
            post_tags = set(post['tags'])
            cur_src_tags = src_tags & post_tags
            if cur_src_tags:
                todo.append(post)
            if dest_tag in post_tags:
                dest_count += 1
        if not todo:
            return
        if confirm:
            src_count = len(todo)
            msg = 'Coalesce %s (%s) to %s (%s)?' % (', '.join(src_tags),
                                                    src_count,
                                                    dest_tag,
                                                    dest_count)
            default_confirm = (src_count * 2) < dest_count
            cur_confirm = get_user_confirmation(msg, default=default_confirm)
            if not cur_confirm:
                return
        pb = ProgressBar(
            widgets=[Percentage(),
                     ' ', Bar(),
                     ' ', SimpleProgress()],
            maxval=len(todo)).start()
        pb.update(0)

        for i, post in enumerate(todo):
            cur_tags = post['tags']
            new_tags = []
            dest_tag_added = False
            for tag in cur_tags:
                if tag in src_tags:
                    if not dest_tag_added:
                        if dest_tag not in cur_tags:
                            new_tags.append(dest_tag)
                        dest_tag_added = True
                    continue
                new_tags.append(tag)
            resp = self.client.edit_post(blog.blog_name,
                                         id=post['id'],
                                         tags=new_tags)
            post['tags'] = new_tags
            pb.update(i + 1)
            #import pdb;pdb.set_trace()
        blog.save()

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
        add_arg('--site', required=True,
                help='the name of the target tumblr site')
        add_arg('--debug', action="store_true",
                help='enable debug console on errors')
        add_arg('--home', default=DEFAULT_HOME_PATH,
                help='grumblr home path, with cached blogs, config, etc.'
                ' defaults to ~/.grumblr')
        add_arg('--conc', default=DEFAULT_CONCURRENCY,
                help='number of concurrent requests to allow during fetches')

        coal_prs = subprs.add_parser('coalesce',
                                     help='coalesce a set of tags')
        add_arg = coal_prs.add_argument
        add_arg('coalesce_tags', metavar='tag',
                nargs='+', help="a tag to merge into the last tag")
        coal_prs = subprs.add_parser('coalesce_lower',
                                     help='coalesce all tags to lowercase'
                                     '(if lowercase is already in use)')
        coal_prs = subprs.add_parser('coalesce_plural',
                                     help='coalesce all tags to plural'
                                     '(if plural is already in use)')

        return prs

    @classmethod
    def from_args(cls):
        kwarg_map = {'site': 'blog_name',
                     'conc': 'concurrency',
                     'home': 'home_path'}
        prs = cls.get_argparser()
        kwargs = dict(prs.parse_args()._get_kwargs())
        for src, dest in kwarg_map.items():
            kwargs[dest] = kwargs.pop(src)
        return cls(**kwargs)


def _proc_untagged(posts):
    untagged = OMD(sorted([p for p in posts.iteritems() if not p[1]['tags']],
                          key=lambda p: p[1]['timestamp']))
    for i, p in enumerate(untagged.values()):
        print i, '-', 'http://tumblr.com/edit/%s' % p['id']


# TODO: sort tags by length, check on necessity of longest and shortest

if __name__ == '__main__':
    main()
