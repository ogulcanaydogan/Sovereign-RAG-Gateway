# Sovereign RAG Gateway - Türkçe Proje Özeti

## 1) Bu proje ne işe yarıyor?
Sovereign RAG Gateway, uygulama ile LLM sağlayıcısı (OpenAI, Azure OpenAI, Anthropic vb.) arasına konan bir kontrol katmanıdır.

Kısaca:
- Uygulama doğrudan modele gitmez, önce gateway'e gelir.
- Gateway, isteği güvenlik/politika açısından değerlendirir.
- Uygunsa gerekli dönüşümleri ve redaksiyonu uygular, sonra provider'a gönderir.
- Sonucu dönerken de iz, kanıt ve denetim kaydı üretir.

Bu sayede "model cevap verdi" seviyesinden "hangi kuralla izin verildi/engellendi, ne redakte edildi, hangi kaynaklar kullanıldı, maliyet ne oldu" seviyesine çıkılır.

## 2) Neden böyle bir şeye ihtiyaç var?
LLM uygulamalarında temel sorun şudur:
- Verinin bir kısmı hassastır (PHI/PII).
- Farklı tenant'lar (müşteriler/ekipler) aynı altyapıyı paylaşır.
- RAG ile dış kaynaklardan veri çekilir; yanlış kaynağa erişim riski vardır.
- Olay sonrası "tam olarak ne oldu?" sorusuna dağınık loglarla cevap vermek zordur.

Bu proje, bu riskleri "uygulama koduna dağılmış kurallar" yerine merkezi ve test edilebilir bir katmanda çözmek için yapıldı.

## 3) Kime hitap ediyor?
- Platform ekipleri
- Security ekipleri
- SRE ekipleri
- Regüle alanlarda çalışan AI uygulama ekipleri

Özellikle şu sorulara net cevap isteyen ekipler için:
- İstek neden bloklandı?
- Hangi veri dışarı çıktı?
- Hangi politikaya göre model seçildi?
- Olayı sonradan kanıt paketine dökebilir miyiz?

## 4) Sistem nasıl çalışıyor? (İstek akışı)
Bir `POST /v1/chat/completions` isteğinde özet akış:

1. İstek gateway'e gelir.
2. `Authorization` ve tenant/user/classification header'ları doğrulanır.
3. Request ID üretilir ve tüm zincire bağlanır.
4. OPA policy değerlendirmesi yapılır (`allow/deny/transform`).
5. Gerekirse transform uygulanır (`set_max_tokens`, `override_model`, `prepend_system_guardrail`).
6. Girdi redaksiyondan geçer (PHI/PII maskeleme).
7. RAG açıksa connector policy kontrolü ile retrieval yapılır, citation verileri hazırlanır.
8. Provider seçimi (routing/budget/fallback) yapılır.
9. Provider çağrısı atılır.
10. Çıktı redaksiyondan geçebilir, cevap normalize edilir.
11. Audit event yazılır (hash zinciri + karar izi + kullanım maliyeti).
12. Tracing/metrics/loglar yayınlanır.

## 5) Ana teknik bileşenler

### 5.1 API ve uyumluluk
- OpenAI-compatible endpointler:
  - `/v1/chat/completions`
  - `/v1/embeddings`
  - `/v1/models`
- Deterministic error envelope:
  - `error.code`
  - `error.message`
  - `error.type`
  - `error.request_id`

### 5.2 Policy enforcement (OPA, fail-closed)
- OPA tarafı karar veremezse fail-closed yaklaşımı uygulanır.
- Policy sonuçları yalnız "allow/deny" değil, "transform" da içerir.
- Böylece governance, response sonrası değil request path üzerinde çalışır.

### 5.3 Redaction motoru
- Regex/pattern tabanlı PHI/PII tespiti.
- Input ve output redaction sayıları ayrı izlenir.
- Geriye dönük uyumluluk için aggregate `redaction_count` korunur.

### 5.4 RAG ve connector katmanı
- Connector tabanlı retrieval:
  - filesystem
  - postgres/pgvector
  - s3
  - confluence
  - jira
  - sharepoint
- Source-level policy sınırları uygulanır.
- Yanıta citation extension eklenir.

### 5.5 Audit ve evidence
- Hash-chained audit event modeli.
- Request replay/evidence bundle üretimi:
  - `bundle.json`
  - `bundle.sha256`
  - `bundle.sig`
  - `bundle.md`
  - `events.jsonl`
- Offline signature verification runbook mevcut.

### 5.6 Operasyonel güvenilirlik
- Rate limit + budget enforcement
- Webhook event dispatch (best effort)
- OTel tracing + metrics + structured JSON logs
- Kind smoke, rollback drill, release-verify, ga-readiness gibi CI kapıları

## 6) Bu repo boyunca nelerle uğraştık? (Pratik iş yükü)
Bu projede asıl emek "feature eklemekten" çok "kontrol zincirini sağlamlaştırmak" tarafına gitti.

Başlıca çalışma başlıkları:

1. OpenAI-compatible gateway iskeleti
- FastAPI tabanı, health/readiness endpointleri
- auth, request-id, error contract

2. Runtime governance hattı
- policy hook + transform executor
- fail-closed davranışları

3. Redaction + audit birleştirmesi
- redaction sonuçlarını denetim kayıtlarına bağlama
- payload hash alanları ve zincir doğruluğu

4. RAG policy gates + citation
- connector erişim kısıtları
- yanıt içine kaynak/citation ekleme

5. Release integrity ve kanıt otomasyonu
- release asset contract kontrolleri
- signature/public key doğrulamaları
- historical sweep (son N release doğrulama)
- weekly evidence raporu ve snapshot üretimi

6. Operasyonel test ve geri alma (rollback)
- kind üstünde deploy-smoke
- rollback drill script + workflow + rapor

## 7) En zor kısımlar ve nasıl çözüldü?

### 7.1 "Çalışıyor" ile "kanıtlanabilir çalışıyor" arasındaki fark
Sistem çalışsa bile dışarıdan doğrulanabilir kanıt üretemiyorsa operasyonel güven düşük kalır.

Çözüm:
- release artifact setini zorunlu hale getiren kontroller
- SHA/signature/public key doğrulama
- haftalık rapora otomatik kanıt bağlantıları

### 7.2 CI flaky davranışları (özellikle kind)
Ephemeral cluster kurulumlarında zaman zaman checksum/kurulum kaynaklı kırılmalar olabilir.

Çözüm:
- script tabanlı kurulum + retry/backoff
- failure durumunda diagnostics artifact toplama

### 7.3 GA promotion güvenliği
GA tag'in rastgele bir commit'ten çıkması riskli.

Çözüm:
- same-commit `release-verify` gate
- GA tag'lerde workflow geçmediyse release publish engeli

## 8) Bu proje ne değildir?
- Genel amaçlı APM alternatifi değildir.
- "PHI/PII'yi %100 yakalar" iddiası yoktur.
- Kurumsal IAM/data governance süreçlerinin yerine geçmez.
- Tüm provider özelliklerini birebir kopyalama hedefi yoktur.

## 9) Bugün geldiğimiz nokta
Bu döngüde hedeflenen operasyonel kapanış tamamlandı:
- `v0.8.0-alpha.1` prerelease yayımlandı.
- Backlog maddeleri kapatıldı.
- Kanıt workflow'ları ve release doğrulamaları çalışır durumda.
- Roadmap üzerinde ilgili "Next" maddeleri kapalı.

Not: "Tamamlandı" ifadesi, bu sprint/hedef kapsamı içindir. Ürün geliştirme doğası gereği bir sonraki iterasyon backlog'u her zaman açılabilir.

## 10) Kısa, teknik olmayan özet (2 dakika)
Bu proje, AI sistemlerinde "önce güvenlik ve kontrol" yaklaşımıdır.

Yani:
- Modele neyin gideceğini kontrol eder.
- Gerekirse hassas bilgiyi gizler.
- Hangi kararın neden alındığını kaydeder.
- Olay sonrası kanıt dosyası çıkarır.

Böylece ekipler sadece "cevap üretmek" değil, "güvenli, izlenebilir ve yönetilebilir şekilde cevap üretmek" seviyesine gelir.

