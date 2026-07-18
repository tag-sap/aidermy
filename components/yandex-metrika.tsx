'use client'

import { useEffect } from 'react'

export function YandexMetrika() {
  useEffect(() => {
    // Добавляем скрипт только на клиенте
    const script = document.createElement('script')
    script.type = 'text/javascript'
    script.innerHTML = `
      (function(m,e,t,r,i,k,a){
        m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
        m[i].l=1*new Date();
        for (var j = 0; j < document.scripts.length; j++) {
          if (document.scripts[j].src === r) { return; }
        }
        k=e.createElement(t),a=e.getElementsByTagName(t)[0],
        k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
      })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=110853057', 'ym');

      ym(110853057, 'init', {
        ssr:true,
        webvisor:true,
        clickmap:true,
        ecommerce:"dataLayer",
        referrer: document.referrer,
        url: location.href,
        accurateTrackBounce:true,
        trackLinks:true
      });
    `
    document.head.appendChild(script)

    // Добавляем noscript
    const noscript = document.createElement('noscript')
    noscript.innerHTML = `<div><img src="https://mc.yandex.ru/watch/110853057" style="position:absolute; left:-9999px;" alt="" /></div>`
    document.head.appendChild(noscript)

    return () => {
      // Очистка при размонтировании
      const scripts = document.querySelectorAll('script[src*="mc.yandex"]')
      scripts.forEach(s => s.remove())
    }
  }, [])

  return null
}
