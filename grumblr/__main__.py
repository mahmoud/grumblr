
from grumblr import Grumblr
from ashes import ashes


def main():
    grumbl = Grumblr.from_args()
    try:
        action = grumbl.default_action
        blog_name = grumbl.default_blog_name
        if action == 'fetch':
            grumbl.fetch_blog(blog_name)
        elif action == 'report':
            ashes.register_source('html_report', HTML_REPORT)
            blog = grumbl.load_blog(blog_name)
            rendered = ashes.render('html_report', blog.get_report_dict())
            print rendered.encode('utf-8')
        elif action == 'coalesce':
            print 'coalescing', grumbl.kwargs['coalesce_tags']
            blog = grumbl.load_blog(blog_name)
            grumbl.coalesce_tag(blog, grumbl.kwargs['coalesce_tags'])
        elif action == 'coalesce_lower':
            print 'coalescing tags to their lowercased counterpart'
            blog = grumbl.load_blog(blog_name)
            grumbl.coalesce_tags_to_lower(blog)
        elif action == 'coalesce_plural':
            print 'coalescing tags to their plural counterpart'
            blog = grumbl.load_blog(blog_name)
            grumbl.coalesce_tags_to_plural(blog)
        else:
            raise RuntimeError('unknown action "%s"' % action)
    except Exception:
        if grumbl.debug:
            import pdb;pdb.post_mortem()
        else:
            raise


HTML_REPORT = """\
<p>{blog_name} has {post_count}+ posts, {tag_percent}% of which are tagged with {tag_count}+ tags, with an average of {tag_post_ratio} tags per post:
  <ul>
  {@iterate key=tag_count_map}
  <li><a href="http://{blog_domain}/tagged/{$key}">{$key}</a> ({$value})</li>{/iterate}
  </ul>
</p>
"""

main()
