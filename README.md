## cf-speed-dns是什么?
CloudflareSpeedTest 推送「每5分钟自选优选 IP」获取Cloudflare CDN 延迟和速度最快 IP ！

## cf-speed-dns有哪些功能？
* CloudflareSpeedTest，在线推送页面。[https://ip.164746.xyz](https://ip.164746.xyz){:target="_blank"}
* [GcsSloop](http://www.gcssloop.com){:target="_blank"}
* CloudflareSpeedTest，Top3接口。[https://ip.164746.xyz/ipTop.html](https://ip.164746.xyz/ipTop.html){:target="_blank"}
* 实时域名解析推送，待开发。

## 接口请求
```javascript
curl -s "https://ip.164746.xyz/ipTop.html" | sed -n 's|<td>\(.*\)</td>|\1|p'
```
## 返回
```javascript
104.16.217.122, 104.18.201.187, 104.17.207.39
```
