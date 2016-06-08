import json
import logging
from random import random
from datetime import datetime
from scrapy import Spider, Request
from HTMLParser import HTMLParser as hp
from cookie import Cookie

class AccountSpider(Spider):
    """
    The AccountSpider class will use weixin.sogou.com to search the official
    accounts. And get the first ten article infomation of each official
    account.
    """
    name = 'weixin'
    article_infos = {}
    not_found = "Not Found"
    cookie_pool = Cookie()

    def start_requests(self):
        """
        Actually, it's better to use __init__ to pass the attributes. But I've
        tried and failed. So I use scrapy settings for a workaround.
        """
        # Get random start url
        random_start_urls = [
            "http://weixin.sogou.com/weixin?type=1&ie=utf8&_sug_=n&_sug_type_=&query=",
            "http://weixin.sogou.com/weixin?query="
        ]
        self.start_urls = map(lambda x: random_start_urls[int(random() * len(random_start_urls))] + x, self.settings.get('ACCOUNT_LIST'))

        for url in self.start_urls:
            yield Request(url, cookies=self.cookie_pool.fetch_one(), callback=self.parse)

    def parse(self, response):
        """
        Parse the result from the main search page and crawl into each result.
        """
        logger = logging.getLogger(response.url[-6:])
        logger.debug(str("Current cookie: " + str(self.cookie_pool.current())))
        if "/antispider/" in response.url:
            cookie = self.cookie_pool.get_banned()
            if cookie:
                logger.debug(str("Got banned. Using new cookie: " + str(cookie)));
                yield Request(response.url, cookies=cookie, callback=self.parse)
            else:
                yield {
                    u"error": u"Seems our IP was banned. Caught by WeChat Antispider: {}".format(response.url),
                    u"date" : unicode(datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                }
        else:
            self.cookie_pool.set_return_header(response.headers.getlist('Set-Cookie'))
            # only query first account
            account_url = response.urljoin(response.xpath('//div[@class="results mt7"]/div[contains(@class, "wx-rb")]/@href').extract_first())
            yield Request(account_url, callback=self.parse_account)

    def parse_account(self, response):
        """
        Parse the account page and crawl into each article.

        It's worth noting that this account page does not render HTML code from
        very beginning. It use JavaScript and a Json string to render the page
        dynamicly. So we use python-json module to parse the Json string.
        """
        nickname = response.xpath('//div/strong[contains(@class, "profile_nickname")]/text()').extract_first(default=self.not_found).strip()
        msgJson  = response.xpath('//script[@type="text/javascript"]/text()')[2].re(r'var msgList = \'(.*)\'')[0]
        articles = json.loads(msgJson)['list']
        for article in articles:
            appinfo = article['app_msg_ext_info']
            cominfo = article['comm_msg_info']
            # Unescape the HTML tags twice
            url  = "http://mp.weixin.qq.com/s?" + hp().unescape(hp().unescape(appinfo['content_url'][4:]))
            self.article_infos[url] = {
                'cover'  : hp().unescape(hp().unescape(appinfo['cover'])).replace('\\/', '/'),
                'date'   : datetime.fromtimestamp(int(cominfo['datetime'])).strftime('%Y-%m-%d %H:%M:%S'),
                'digest' : appinfo['digest']
            }
            yield Request(url, callback=self.parse_article)
            if u'multi_app_msg_item_list' in appinfo:
                for info in appinfo[u'multi_app_msg_item_list']:
                    url  = "http://mp.weixin.qq.com/s?" + hp().unescape(hp().unescape(info['content_url'][4:]))
                    self.article_infos[url] = {
                        'cover'  : hp().unescape(hp().unescape(info['cover'])).replace('\\/', '/'),
                        'date'   : datetime.fromtimestamp(int(cominfo['datetime'])).strftime('%Y-%m-%d %H:%M:%S'),
                        'digest' : info['digest']
                    }
                    yield Request(url, callback=self.parse_article)

    def parse_article(self, response):
        """
        Finally we've got into the article page. Since response.url is generated
        dynamically, we need to get the permenant URL of the article.
        """
        title  = response.xpath('//div[@id="page-content"]/div/h2/text()').extract_first(default=self.not_found).strip()
        user   = response.xpath('//*[@id="post-user"]/text()').extract_first(default=self.not_found).strip()
        script = response.xpath('//script[contains(text(), "var biz =")]')[0]
        params = ['biz', 'sn', 'mid', 'idx']
        values = map(lambda x:x + '=' + script.re('var ' + x + ' = .*"([^"]*)";')[0], params)
        url    = "http://mp.weixin.qq.com/s?" + reduce(lambda x,y:x+'&'+y, values)
        html   = str.join("\n", response.xpath('//*[@id="js_content"]').extract()).strip()
        info   = self.article_infos[response.url]
        yield {
            u'title'   : unicode(title),
            u'account' : unicode(user),
            u'url'     : unicode(url),
            u'date'    : unicode(info['date']),
            u'cover'   : unicode(info['cover']),
            u'digest'  : unicode(info['digest']),
            u'content' : unicode(html)
        }

    def parse_cookie(self, header_list):
        snuid = ""
        suid = ""
        for header in header_list:
            if 'SNUID' == header.split('=')[0]:
                snuid = header.split('=')[1].split(';')[0]
            if 'SUID' == header.split('=')[0]:
                suid = header.split('=')[1].split(';')[0]
        if "" == snuid:
            return self.cookie
        else:
            return self.cookie_pool.new(snuid, suid)