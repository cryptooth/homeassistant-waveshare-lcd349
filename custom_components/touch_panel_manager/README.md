# Touch Panel Manager (HA Custom Integration)

Home Assistant tarafında bir UI ile ESPHome touch panel cihazlarını konfigüre
etmek için custom_component. Cihazda flash gerekmez — config HA'dan yönetilir,
cihaz ilgili sensor entity'sine abone olur ve LVGL widget'larını ona göre kurar.

## Versiyon Yol Haritası

- **v0.1** *(şu an)* — Scaffold. Config flow ile cihaz adı + iç/dış sıcaklık
  sensoru seçilir. Bir `sensor.<panel_adi>_config` entity'si yaratılır,
  attribute'ları cihaza okutulacak.
- **v0.2** *(yakında)* — OptionsFlow ile dinamik buton/slot ekleme/silme.
  Light, switch, scene, script tipi entity'ler için ayrı seçiciler.
- **v0.3** — ESPHome YAML'ı dinamik subscribe'a çevirme + lambda action dispatcher.
- **v0.4+** — Çoklu sayfa, sahne renk teması, HACS-ready paketleme.

## Kurulum (development)

1. HA config klasörünün altına kopyala:
   ```bash
   cp -r custom_components/touch_panel_manager <HA_CONFIG>/custom_components/
   ```
   (HA add-on kullanıyorsan: `\\<HA_IP>\config\custom_components\` SMB yolu üzerinden).

2. HA'yı yeniden başlat.

3. **Settings → Devices & Services → "Add Integration"** → "Touch Panel Manager" ara.

4. Açılan formda:
   - Panel adı (örn. "Salon Paneli")
   - Dış sıcaklık sensoru (isteğe bağlı)
   - İç sıcaklık sensoru (isteğe bağlı)

5. Sonuç: `sensor.salon_paneli_config` entity'si yaratılır. State'i `configured`,
   attribute'larında seçtiklerin durur.

## Geliştirici Notları

- `manifest.json`: integration metadata, version bump unutma
- `config_flow.py`: UI adımları (voluptuous schema)
- `sensor.py`: ESPHome'un okuyacağı entity (state + attributes)
- `const.py`: tüm sabitler tek dosyada
- `strings.json`: Türkçe çeviri (default), `translations/en.json` İngilizce

## Test

Yeniden başlatma sonrası HA log:
```
INFO touch_panel_manager: Touch Panel Manager kuruldu: Salon Paneli
```

Entity'yi Developer Tools → States'ten kontrol et:
```
sensor.salon_paneli_config
state: configured
attributes:
  outdoor_temp: sensor.disari
  indoor_temp: sensor.salon
  buttons: []
```
