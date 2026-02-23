# SincromisorCLI

かわいいキャラの姿と声になっておしゃべりできるサービス基盤[Sincromisor](https://github.com/Phenomer/Sincromisor)のCLIクライアントです。ブラウザなしで音声認識・音声合成が利用できます。

## 必要なもの

* [Sincromisorサーバー](https://github.com/Phenomer/Sincromisor)
* 音声入出力デバイスをもつ環境
* サーバーに到達できるネットワーク

## インストール

### 依存ライブラリのインストール

```sh
$ sudo apt install libportaudio2
```

Pythonパッケージ管理には[uv](https://github.com/astral-sh/uv)を使用しています。

```sh
$ uv sync
```

### WSL2の場合の追加インストール
PortAudioがPulseAudio経由で音声入出力できるよう、ライブラリを追加でインストールする必要があります。

```sh
$ sudo apt install libasound2-plugins
```

### サウンドデバイスのテスト

`SoundDeviceList.py`を実行すると、利用できるサウンドデバイス一覧と、デフォルトのサウンドデバイスが得られます。

```sh
$ uv run python SoundDeviceList.py
```

```sh
...

Default Input Device:
  Device 1:
    Name: Microphone (2- Shure MV7)
    Host API: 0
    Max Input Channels: 1
    Default Sample Rate: 44100.0

Default Output Device:
  Device 5:
    Name: Headphones (2- Shure MV7)
    Host API: 0
    Max Input Channels: 0
    Default Sample Rate: 44100.0
```

### config.ymlの作成

SincromisorClientの設定ファイルを作成します。

* `examples/config.yml`をコピーし、環境に合わせて`config_url`（推奨）または`offer_url` / `candidate_url` / `ice_server` / `ice_servers`、`talk_mode`を編集してください。
  * `config_url`には Sincromisor の `GET /api/v1/RTCSignalingServer/config.json` を指定します。
  * `config_url`を指定すると、`offerURL` / `candidateURL` / `iceServers` をサーバー設定から自動取得します。
  * `candidate_url`を省略した場合は、`offer_url`の末尾`/offer`を`/candidate`に置換して利用します。
* `sender_device`と`receiver_device`の`device`については、`null`にしておくとOSのデフォルトのものが選ばれます。
* 各デバイスのチャンネル数やサンプリングレート、データ型、ブロックサイズは、そのままにしておいてください。
* talk_modeは`sincro`もしくは`chat`のいずれかです。

```sh
$ cp examples/config.yml .
```

```yaml
config_url: "https://sincromisor.example.com/api/v1/RTCSignalingServer/config.json"
# 明示指定したい場合のみ以下を使う（config_url指定時は通常不要）
# offer_url: "https://sincromisor.example.com/api/v1/RTCSignalingServer/offer"
# candidate_url: "https://sincromisor.example.com/api/v1/RTCSignalingServer/candidate"
# ice_server: "stun:stun.example.com:3478"
# ice_servers:
#   - urls: ["stun:stun.example.com:3478"]
talk_mode: "sincro"
sender_device:
    channels: 1
    samplerate: 48000
    dtype: "int16"
    blocksize: 960
    device: null
receiver_device:
    channels: 2
    samplerate: 48000
    dtype: "int16"
    blocksize: 960
    device: null
```

## SincromisorClientを実行

`uv run`から`SincromisorClient.py`を実行します。

```sh
$ uv run python SincromisorClient.py
```

マイクに対し適当に話しかけると、音声認識の結果と、合成した音、音声に合わせたテロップ用テキストが出力されます。

```python
['text_ch', {'session_id': '01J8C7TZG25HF1H9552BRF0QP6', 'speech_id': 5, 'sequence_id': 12, 'start_at': 1726987780.1253614, 'confirmed': False, 'recognizedResult': [['音声', 0.88134765625], ['に', 0.9609375], ['。', 0.73876953125], ['</s>', 1.0]], 'resultText': '音声に。'}]
['text_ch', {'session_id': '01J8C7TZG25HF1H9552BRF0QP6', 'speech_id': 5, 'sequence_id': 13, 'start_at': 1726987780.5311143, 'confirmed': False, 'recognizedResult': [['音声', 0.50927734375], ['認識', 0.9658203125], ['。', 0.92431640625], ['</s>', 1.0]], 'resultText': '音声認識。'}]
['text_ch', {'session_id': '01J8C7TZG25HF1H9552BRF0QP6', 'speech_id': 5, 'sequence_id': 15, 'start_at': 1726987780.5311143, 'confirmed': True, 'recognizedResult': [['音声', 0.99951171875], ['認識', 1.0], ['システム', 0.99951171875], ['の', 0.88037109375], ['。', 0.5849609375], ['</s>', 1.0]], 'resultText': '音声認識システムの。'}]
['text_ch', {'session_id': '01J8C7TZG25HF1H9552BRF0QP6', 'speech_id': 6, 'sequence_id': 16, 'start_at': 1726987781.4800775, 'confirmed': False, 'recognizedResult': [['。', 0.012542724609375], ['</s>', 0.84912109375]], 'resultText': '。'}]
['text_ch', {'session_id': '01J8C7TZG25HF1H9552BRF0QP6', 'speech_id': 6, 'sequence_id': 17, 'start_at': 1726987781.4800775, 'confirmed': True, 'recognizedResult': [['テスト', 0.9091796875], ['です', 0.98388671875], ['。', 0.9970703125], ['</s>', 1.0]], 'resultText': 'テストです。'}]
['telop_ch', {'timestamp': 0.0, 'message': '音声認識システムの。', 'vowel': None, 'text': None, 'length': 0.1, 'new_text': True}]
['telop_ch', {'timestamp': 0.1, 'message': '音声認識システムの。', 'vowel': 'o', 'text': 'オ', 'length': 0.15235960483551025, 'new_text': True}]
['telop_ch', {'timestamp': 0.25999999999999995, 'message': '音声認識システムの。', 'vowel': 'N', 'text': 'ン', 'length': 0.07555720955133438, 'new_text': True}]
['telop_ch', {'timestamp': 0.34, 'message': '音声認識システムの。', 'vowel': 'e', 'text': 'セ', 'length': 0.1649692952632904, 'new_text': True}]
['telop_ch', {'timestamp': 0.5000000000000001, 'message': '音声認識システムの。', 'vowel': 'e', 'text': 'エ', 'length': 0.0805792436003685, 'new_text': True}]
['telop_ch', {'timestamp': 0.5800000000000002, 'message': '音声認識システムの。', 'vowel': 'i', 'text': 'ニ', 'length': 0.1659422069787979, 'new_text': True}]
['telop_ch', {'timestamp': 0.7400000000000003, 'message': '音声認識システムの。', 'vowel': 'N', 'text': 'ン', 'length': 0.07122189551591873, 'new_text': True}]
['telop_ch', {'timestamp': 0.8200000000000004, 'message': '音声認識システムの。', 'vowel': 'I', 'text': 'シ', 'length': 0.094368115067482, 'new_text': True}]
['telop_ch', {'timestamp': 0.9200000000000005, 'message': '音声認識システムの。', 'vowel': 'i', 'text': 'キ', 'length': 0.13086148351430893, 'new_text': True}]
['telop_ch', {'timestamp': 1.0400000000000005, 'message': '音声認識システムの。', 'vowel': 'i', 'text': 'シ', 'length': 0.13497281819581985, 'new_text': True}]
['telop_ch', {'timestamp': 1.1800000000000006, 'message': '音声認識システムの。', 'vowel': 'U', 'text': 'ス', 'length': 0.10108337551355362, 'new_text': True}]
['telop_ch', {'timestamp': 1.2800000000000007, 'message': '音声認識システムの。', 'vowel': 'e', 'text': 'テ', 'length': 0.13650678098201752, 'new_text': True}]
['telop_ch', {'timestamp': 1.4200000000000008, 'message': '音声認識システムの。', 'vowel': 'u', 'text': 'ム', 'length': 0.13260924816131592, 'new_text': True}]
['telop_ch', {'timestamp': 1.560000000000001, 'message': '音声認識システムの。', 'vowel': 'o', 'text': 'ノ', 'length': 0.21395232528448105, 'new_text': True}]
['telop_ch', {'timestamp': 0.0, 'message': 'テストです。', 'vowel': None, 'text': None, 'length': 0.1, 'new_text': True}]
['telop_ch', {'timestamp': 0.1, 'message': 'テストです。', 'vowel': 'e', 'text': 'テ', 'length': 0.14856474101543427, 'new_text': True}]
['telop_ch', {'timestamp': 0.25999999999999995, 'message': 'テストです。', 'vowel': 'U', 'text': 'ス', 'length': 0.10392764955759048, 'new_text': True}]
['telop_ch', {'timestamp': 0.36000000000000004, 'message': 'テストです。', 'vowel': 'o', 'text': 'ト', 'length': 0.127304345369339, 'new_text': True}]
['telop_ch', {'timestamp': 0.48000000000000015, 'message': 'テストです。', 'vowel': 'e', 'text': 'デ', 'length': 0.13800779730081558, 'new_text': True}]
['telop_ch', {'timestamp': 0.6200000000000002, 'message': 'テストです。', 'vowel': 'U', 'text': 'ス', 'length': 0.18415472656488419, 'new_text': True}]
```

## 音声認識結果テキスト・テロップのテキストの処理をカスタマイズ

`SincromisorRTCClient`の`text_ch_on_message`と`telop_ch_on_message`をoverrideしてカスタマイズできます。

```python
class CustomizedSincromisorClient(SincromisorRTCClient):
    async def text_ch_on_message(self, channel: RTCDataChannel, message: str) -> None:
        print([channel.label, json.loads(message)])

    async def telop_ch_on_message(self, channel: RTCDataChannel, message: str) -> None:
        print([channel.label, json.loads(message)])
```
