## cf-speed-dns是什么?
CloudflareSpeedTest 推送「每5分钟自选优选 IP」获取Cloudflare CDN 延迟和速度最快 IP ！

## cf-speed-dns有哪些功能？
* CloudflareSpeedTest，在线推送页面。[https://ip.164746.xyz](https://ip.164746.xyz)
* CloudflareSpeedTest，Top接口。[https://ip.164746.xyz/ipTop.html](https://ip.164746.xyz/ipTop.html)
* 实时域名解析推送，fork。[https://github.com/ZhiXuanWang/cf-speed-dns-push](https://github.com/ZhiXuanWang/cf-speed-dns-push)
* Action配置，Actions secrets and variables 添加 DOMAIN(例如：174746.xyz)，SUB_DOMAIN（例如：dns），SECRETID（xxxxx），SECRETKEY（xxxxx）。

## 接口请求
```javascript
curl 'https://ip.164746.xyz/ipTop.html'
```
## 返回
```javascript
104.16.204.6,104.18.103.125
```

## 感谢
[XIU2](https://github.com/XIU2/CloudflareSpeedTest)、[ddgth](https://github.com/ddgth/cf2dns)
