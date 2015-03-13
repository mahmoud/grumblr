
from grumblr import Grumblr
from ashes import ashes


def main():
    grumbl = Grumblr.from_args()
    action = grumbl.default_action
    blog_name = grumbl.default_blog_name
    if action == 'fetch':
        grumbl.fetch_blog(blog_name)
    elif action == 'report':
        ashes.register_source('html_report', HTML_REPORT)
        blog = grumbl.load_blog(blog_name)
        rendered = ashes.render('html_report', blog.get_report_dict())
        print rendered.encode('utf-8')
    else:
        raise RuntimeError('unknown action "%s"' % action)


HTML_REPORT = """\
<p>{blog_name} has {post_count}+ posts, {tag_percent}% of which are tagged with {tag_count}+ tags, with an average of {tag_post_ratio} tags per post:
  <ul>
  {@iterate key=tag_count_map}
  <li><a href="http://{blog_domain}/tagged/{$key}">{$key}</a> ({$value})</li>{/iterate}
  </ul>
</p>
"""

main()
