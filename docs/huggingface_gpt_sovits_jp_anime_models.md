# GPT-SoVITS Models and Weights for Japanese Anime Characters and Voice Actors on Hugging Face

Search date: **2026-09-03 (Asia/Shanghai)**

## Scope and methodology

- Searched the Hugging Face Models API for variants including `GPT-SoVITS`, `GPTSoVITS`, `gptsovits`, and `gpt_sovits`. After normalization and deduplication, **279 publicly discoverable repositories** were inspected.
- Each repository's model card, tags, and complete file tree were reviewed, with particular attention to weights and archives such as `.ckpt`, `.pth`, `.safetensors`, `.zip`, and `.7z` files.
- An "explicit match" means that the model card, repository name, weight filename, reference-audio filename, or language tags clearly support at least one of the following: a Japanese anime character, a Japanese game or visual-novel character, an explicitly Japanese character voice track, or a Japanese voice actor as the voice source.
- "Verification required" means that the character matches the scope, but the repository does not identify the training track's language, version, or voice actor. These entries are retained to maximize recall.
- The main tables include only Hugging Face repositories that actually contain weights or weight archives. Repositories containing only code, base models, inference bundles, datasets, or external download links without character weights are excluded.
- A repository's declared `model license` applies only to the software or files covered by that declaration. It **does not** establish rights to the character, dialogue, performer's voice, or commercial use. Review the model card, rights holder's rules, and applicable law before downloading or using a model.

> Completeness boundary: "all" means entries discoverable through Hugging Face's public index at the time of this search and identifiable from public metadata. Coverage cannot be guaranteed for private, deleted, unindexed, subsequently added repositories, or repositories whose names and model cards contain no GPT-SoVITS indicators.

## A. Explicit matches: anime, Japanese games, and visual-novel characters

| # | Character or voice source | Work or evidence | Weight format and notes | Citation |
|---:|---|---|---|---|
| 1 | Nene Kusanagi (CV: Machico) | *Project SEKAI: Colorful Stage! feat. Hatsune Miku*; the model card explicitly identifies the voice source and CV | Multiple GPT `.ckpt` and SoVITS `.pth` weights; zh/ja/en | [Model card and weights](https://huggingface.co/MomoyamaSawa/GPT-SoVITS_KusanagiNene) |
| 2 | ATRI | Assets from *ATRI -My Dear Moments-*; the model card reports approximately 112 minutes of training data | `atri-e10.ckpt` and `atri_e25_s5250.pth` | [Model card and weights](https://huggingface.co/2DIPW/ATRI_GPT-SoVITS) |
| 3 | Chtholly | Character from *WorldEnd: What Do You Do at the End of the World? Are You Busy? Will You Save Us?*; the model card links a character-voice dataset | GPT-SoVITS v2 GPT and SoVITS weights | [Model card and weights](https://huggingface.co/Chtholly-dev/Chtholly-GPT-SoVITS) |
| 4 | Hitori Gotoh, Nijika Ijichi, and Ikuyo Kita | *Bocchi the Rock!*; the model card explicitly says the models were trained on character voices from the TV anime | v2ProPlus and v4; multiple `.ckpt` and `.pth` versions; ja/en/zh | [Model card and weights](https://huggingface.co/lpkpaco/Bocchi-The-Rock-GPT-SoVITS-Models) |
| 5 | Tomoko Kuroki | Character from *WataMote*; the repository also provides character audio samples | GPT-SoVITS v2 `.ckpt` and `.pth` | [File tree and samples](https://huggingface.co/quarterturn/kuroki_tomoko_gpt_sovits_v2/tree/main) |
| 6 | Mahiru Shiina | Reference-audio filenames are organized by season-two episode (`mahiru_s2_ep...`) | v2ProPlus GPT and SoVITS weights with numerous reference clips | [File tree and reference audio](https://huggingface.co/canhday/Mahiru_Voice_Model_GPTSoVITS/tree/main) |
| 7 | Mash Burnedead | Character from *Mashle: Magic and Muscles*; repository tags include ja/en | `Mash_Burnedead.zip` | [Model card and weight archive](https://huggingface.co/TexX/GPT-SoVITS-Models) |
| 8 | Son Goku | *Dragon Ball* character | Multiple GPT and SoVITS checkpoints | [File tree](https://huggingface.co/ryantokmanmokmtm/GPT-SoVITS-songoku-model/tree/main) |
| 9 | Frieza | *Dragon Ball* character | Multiple GPT and SoVITS checkpoints | [File tree](https://huggingface.co/ryantokmanmokmtm/GPT-SoVITS-freeza-model/tree/main) |
| 10 | Nene Ayachi and Mayu Shikibe | *Sabbat of the Witch* and *Riddle Joker*; the model card explicitly lists the works | `nene` and `mayu` GPT and SoVITS weights; the repository also contains non-Japanese characters | [Model card and weights](https://huggingface.co/terryzzz/My_GPT_SoVITS_Models) |
| 11 | Iroha Tamaki | *Magia Record: Puella Magi Madoka Magica Side Story* character | Multiple GPT `.ckpt` and SoVITS `.pth` checkpoints | [File tree](https://huggingface.co/MOTTTTT2610/Tamaki_Iroha_GPT_SoVITS_model/tree/main) |
| 12 | Yachiyo Nanami | *Magia Record: Puella Magi Madoka Magica Side Story* character | Multiple GPT `.ckpt` and SoVITS `.pth` checkpoints | [File tree](https://huggingface.co/MOTTTTT2610/Nanami_Yachiyo_GPT_SoVITS_model/tree/main) |
| 13 | Hakua Hiiragi | Japanese game character; the model card says in-game voices were used and provides three differently filtered dataset versions | Multiple GPT and SoVITS weights | [Model card and weights](https://huggingface.co/MondMeer/GPT-SoVITS-HiiragiHakua) |
| 14 | Hotaru Minazuki | Japanese game character; the model card explicitly says the training data consists of in-game voices | GPT and SoVITS weights | [Model card and weights](https://huggingface.co/MondMeer/GPT-SoVITS-MinazukiHotaru) |
| 15 | Minto | Visual-novel character; the model card explicitly identifies the voice material as the "tender" route or style | Multiple `.ckpt` and `.pth` checkpoints with segmented data | [Model card and weights](https://huggingface.co/overload7015/GPT-SoVits-Minto-tender-1197) |
| 16 | Sora Kasugano, ATRI, Minto, Rindou Ruri, Sumizome Nozomi, Tenma Hasumi, and Vikala | The file tree directly lists weights for multiple Japanese anime, game, or visual-novel characters | One GPT/SoVITS pair per character | [File tree](https://huggingface.co/hsgwktb/GPT-SoVITS_Models/tree/main) |
| 17 | Rin Misakura | The repository name explicitly references *Sakura no Uta* | GPT and SoVITS weights | [File tree](https://huggingface.co/hsgwktb/GPT-SoVITS_Models_sakura_no_uta/tree/main) |
| 18 | Shinku; an internal weight is also named `apeiria` | Japanese visual-novel character repository; the repository and internal weight names do not fully agree, so auditioning is recommended | Two GPT and SoVITS weight sets | [File tree](https://huggingface.co/kmichiru/GPT-SoVITS-Shinku/tree/main) |
| 19 | Linne | The model card explicitly reports 1,293 extracted audio clips from the game *ISLAND* | v2ProPlus GPT and SoVITS weights | [Model card and weights](https://huggingface.co/heze222333/Linne-GPT-SOVITS) |
| 20 | Rinko Shirokane | *BanG Dream!*; the file tree contains `Rinko` data and character weights | v2ProPlus `.ckpt` and `.pth` with Japanese dialogue audio | [File tree](https://huggingface.co/Wanlau/GPT-SoVITS_BanGDream/tree/main) |
| 21 | Murasame | Character from *Senren Banka* | GPT `.ckpt` and SoVITS `.pth` | [File tree](https://huggingface.co/cubewhy/Murasame-chan-GPT-SoVits/tree/main) |
| 22 | Tachibana Sherry | Japanese game character; the model card describes training from in-game audio and provides dialogue mappings and reference audio | v2ProPlus GPT and SoVITS weights | [Model card and weights](https://huggingface.co/gomico/tachibana_sherry_gpt-sovits) |
| 23 | Sakuraba Ema | Japanese game character; the model card describes training from in-game audio and provides dialogue mappings and reference audio | v2ProPlus GPT and SoVITS weights | [Model card and weights](https://huggingface.co/gomico/sakuraba_ema_gpt-sovits) |
| 24 | "TnS Kotomi" | The filename explicitly contains `TnS_kotomi`; the model card does not identify the full work title | Multiple GPT and SoVITS checkpoints; auditioning is required to verify the exact character | [File tree](https://huggingface.co/scientificworld/TnS_gpt_sovits_models/tree/main) |
| 25 | Artoria Caster and Kanade Yoisaki | Characters from *Fate/Grand Order* and *Project SEKAI* | `Artoria_Caster_TTS_v1.zip` and three Kanade Yoisaki archives | [File tree](https://huggingface.co/hj0816/gpt_sovits_models/tree/main) |
| 26 | Danganronpa characters: Aoi Asahina, Byakuya Togami, Kyoko Kirigiri, and Makoto Naegi | Filenames explicitly identify *Danganronpa* characters | Separate GPT-SoVITS `.zip` archive for each character | [TheRC4 file tree](https://huggingface.co/TheRC4/GPT-SoVITSModels/tree/main) |
| 27 | Byakuya Togami | *Danganronpa* character | `ByakuyaTogamiGPT-SoVITS.zip` | [File tree](https://huggingface.co/modelloosrvcc/GPT-SoVITSModels/tree/main) |
| 28 | Kotoko Utsugi | Character from *Danganronpa Another Episode: Ultra Despair Girls* | `KotokoUtsugii.zip` | [File tree](https://huggingface.co/modelloosrvcc/Kotoko_Utsugi_GPT-SOVITS/tree/main) |
| 29 | Nagisa Shingetsu | Character from *Danganronpa Another Episode: Ultra Despair Girls* | `Nagisa.zip` | [File tree](https://huggingface.co/modelloosrvcc/Nagisa_Shingetsu_GPT-SoVITS/tree/main) |
| 30 | Makoto Naegi and Reimu Hakurei | Characters from *Danganronpa* and *Touhou Project* | `Makoto Naegi...zip` and `Reimu Hakurei...zip` | [File tree](https://huggingface.co/MusicBox27/GPT_SoVITS_Models/tree/main) |
| 31 | `tsukasa` (the exact character is not documented) | Repository language tags are ja/en and the archive is named `tsukasa.zip` | GPT-SoVITS weight archive | [Model card and files](https://huggingface.co/sxndypz/gpt-sovits-models) |
| 32 | Seijuro Akashi | *Kuroko's Basketball* character; the repository also contains non-anime characters such as Lara Croft and Max Caulfield | `SeijuroAkashiBySztef.zip` | [File tree](https://huggingface.co/Sztef/GPT-Sovits/tree/main) |
| 33 | Makoto Naegi, Sesshomaru, and Kikyo; also Iono, Lillie, Nessa, Volkner, and other Japanese game characters | Characters from *Danganronpa*, *Inuyasha*, *Pokémon*, and other works; filenames identify the characters, but the voice tracks may be English dubs | Separate `.zip` archive per character | [File tree](https://huggingface.co/EthanRhys/GPT-SoVITS-Models/tree/main) |
| 34 | Multiple characters from Blue Archive, Girls Band Cry, MyGO!!!!!, and Ave Mujica | File paths explicitly group Blue Archive, Girls Band Cry, and MyGO content; Honkai: Star Rail characters are also included | Per-character GPT `.ckpt` and SoVITS `.pth`; language not specified | [File tree](https://huggingface.co/WLWolf56/gpt-sovits-model/tree/main) |
| 35 | Arisu, Momoi Saiba, and Noeri Fujishiro | Blue Archive and other Japanese game characters; archive names identify the characters | `.7z` character-weight archives | [File tree](https://huggingface.co/RinkaEmina/GPT-SoVITS_Sharing/tree/main) |

## B. Explicit Japanese tracks or Japanese character-voice projects not necessarily originating in television anime

| # | Character or voice source | Evidence and scope | Weight format and notes | Citation |
|---:|---|---|---|---|
| 1 | Combined multi-character Japanese *Genshin Impact* model | The file tree contains `Genshin_Impact/JA`, and the model card lists Japanese coverage through version 5.1 | `GPT_GenshinImpact_JA_5.1.ckpt` and `SV_GenshinImpact_JA_5.1.pth` | [Model card and weights](https://huggingface.co/AI-Hobbyist/GPT-SoVits-V2-models) |
| 2 | Furina and Hu Tao (Japanese) | The weight name explicitly contains `FurinaJP3`; Hu Tao is published in the same repository | GPT and SoVITS weights | [File tree](https://huggingface.co/Seagata/Furina_and_Hu_Tao_GPT-SoVITS_model/tree/main) |
| 3 | Sangonomiya Kokomi | The model card has a ja tag and Japanese audio samples | Multiple GPT and SoVITS versions | [Model card, samples, and weights](https://huggingface.co/xiaoheiqaq/GPT-Sovits-models) |
| 4 | Verina | Separate EN, JA, and ZH weights and samples are published | v2ProPlus DPO with separate Japanese GPT and SoVITS weights | [Model card and weights](https://huggingface.co/huggingkot/Verina-GPT-SoVITS-v2ProPlus-DPO-EN-JA-ZH) |
| 5 | Multiple *Uma Musume: Pretty Derby* characters | The model card explicitly identifies voices from the franchise and includes a ja tag; characters include Special Week, Tokai Teio, Rice Shower, and Kitasan Black | Combined multi-character GPT and SoVITS weights | [Model card and weights](https://huggingface.co/UmaDiffusion/uma-voice-gpt-sovits-v2) |
| 6 | Arona | Blue Archive character | v2Pro GPT and SoVITS weights; training language not documented | [File tree](https://huggingface.co/idoldange/arona-gptsovits/tree/main) |
| 7 | Seia Yurizono | Blue Archive character | v2ProPlus GPT and SoVITS weights; no detailed model card | [File tree](https://huggingface.co/l73jiang/Seia-GPT-SOVITS-ProPlus/tree/main) |
| 8 | Misaki Kainoh (inferred from the repository name) | The name matches a Blue Archive character, but no model card is provided | GPT and SoVITS weights plus a `.zip` archive; auditioning is required | [File tree](https://huggingface.co/AndriLawrence/misaki-gpt-sovits/tree/main) |
| 9 | Senko | The weight name is `Senko`, matching the character from *The Helpful Fox Senko-san* | GPT and SoVITS weights; no detailed source documentation | [File tree](https://huggingface.co/HiImNVH/GPT_SoVITS_Models/tree/main) |
| 10 | Rimuru | Character from *That Time I Got Reincarnated as a Slime* | GPT-SoVITS v2 `.ckpt` and `.pth`; language not documented | [File tree](https://huggingface.co/Not-Black/Rimuru-GPT-SoVITS-v2/tree/main) |
| 11 | Yumemizuki Mizuki | *Genshin Impact* character; the model card identifies the character and dataset author | GPT-SoVITS v3 weights and a reference-audio bundle; training language not documented | [Model card and weights](https://huggingface.co/Sprt98/GPT-SoVITS_Yumemizuki_Mizuki) |
| 12 | Furina | *Genshin Impact* character; both the linked dataset and repository language tags indicate English | Multiple `.safetensors` checkpoints; relevant for users seeking the English voice | [Model card and weights](https://huggingface.co/PJMixers-Dev/GPT-SoVITS-Genshin-Impact-Furina) |

## C. Japanese voice characters and Japanese anime-style corpora

These repositories do not strictly represent Japanese anime characters, but they are commonly relevant when searching for Japanese character voices.

| # | Voice source | Description | Weight format and notes | Citation |
|---:|---|---|---|---|
| 1 | Shikoku Metan | Voice character from the Tohoku Zunko and Zundamon project; the model card identifies the character and links the official usage rules | v2Pro with multiple GPT and SoVITS checkpoints | [Model card and weights](https://huggingface.co/4nm1tsu/shikokumetan_GPT-SoVITS) |
| 2 | Zundamon (exVOICE) | Japanese voice character; the repository includes character-specific terms | GPT and SoVITS weights | [File tree](https://huggingface.co/gro-w/gpt-sovits-zundamon-exvoice/tree/main) |
| 3 | Zundamon (normal) | Japanese voice character | GPT and SoVITS weights | [File tree](https://huggingface.co/gro-w/gpt_sovits_zundamon_normal/tree/main) |
| 4 | Zundamon (another training version) | The model card is tagged ja/zh/en | GPT and SoVITS weights | [Model card and weights](https://huggingface.co/zunzunpj/zundamon_GPT-SoVITS) |
| 5 | Zundamon and JVNV F1/F2/M1/M2 | The repository contains a Zundamon character package and four JVNV Japanese voice packages | `.ckpt`, `.pth`, and `.zip` files | [File tree](https://huggingface.co/wok000/gpt-sovits-models/tree/main) |
| 6 | Kasane Teto | The model card explicitly states that the model was trained on Japanese Kasane Teto voice data | GPT-SoVITS v4 `.ckpt` and `.pth` with Japanese reference audio | [Model card and weights](https://huggingface.co/NeatAvocado14/KasaneTeto-GPTSoVITS-V2) |
| 7 | `moe-speech` Japanese multi-speaker corpus | Fine-tuned from the Japanese subset of `litagin/moe-speech`; the model card reports approximately six hours of data and says the model specializes in Japanese | GPT and SoVITS weights; not a single-character model | [Model card and weights](https://huggingface.co/AdamCodd/GPTSoVITS-JP-tts) |
| 8 | 200-hour Japanese prosody-control corpus | Japanese-specific prosody-control fine-tune; not a character-specific model | Two GPT weights and a base SoVITS weight | [Model card and weights](https://huggingface.co/AkitoP/GPT-SoVITS-JA-ProsodyControl_model) |

## D. Anime-style game characters whose training language is explicitly not Japanese or lacks sufficient evidence

These results may fit a broad interpretation of "anime-style character," but they should not be mislabeled as samples of Japanese voice actors.

| # | Character or repository | Known language or uncertainty | Weight format and coverage | Citation |
|---:|---|---|---|---|
| 1 | 52 *Honkai: Star Rail* characters | The model card explicitly points to a Chinese reference dataset | One `.zip` weight archive per character | [Model card and file tree](https://huggingface.co/baicai1145/GPT-SoVITS-STAR) |
| 2 | Large collection spanning *Genshin Impact*, *Honkai: Star Rail*, *Zenless Zone Zero*, *Blue Archive*, and others | Directory and character names are in Chinese; no Japanese sampling claim was found | Numerous per-character GPT and SoVITS weights with reference audio | [File tree](https://huggingface.co/UnlimitedBurst/GPT-SoVITS/tree/main) |
| 3 | Ayaka, Citlali, Firefly, Klee, Nahida, Tribbie, and Yoimiya | The model card is tagged zh; characters are from HoYoverse games | Per-character GPT and SoVITS weights with reference audio | [Model card and weights](https://huggingface.co/BigPancake01/GPT-SoVITS_Mihoyo) |
| 4 | Arknights: Vulpisfoglia | Model card languages are zh/en | GPT and SoVITS weights | [Model card and weights](https://huggingface.co/None1145/GPT-SoVITS-Vulpisfoglia) |
| 5 | Arknights: Theresa | Model card languages are zh/en | GPT and SoVITS weights | [Model card and weights](https://huggingface.co/None1145/GPT-SoVITS-Theresa) |
| 6 | Arknights: Theresa Recording | Game and Bilibili recordings; Japanese is not identified | GPT and SoVITS weights | [Model card and weights](https://huggingface.co/None1145/GPT-SoVITS-Theresa-Recording) |
| 7 | Arknights: Lappland | Model card languages are zh/en | GPT and SoVITS weights | [Model card and weights](https://huggingface.co/None1145/GPT-SoVITS-Lappland) |
| 8 | Arknights: Lappland the Decadenza | Model card languages are zh/en | GPT and SoVITS weights | [Model card and weights](https://huggingface.co/None1145/GPT-SoVITS-Lappland-the-Decadenza) |
| 9 | Arknights: Rosmontis | Model card languages are zh/en | GPT and SoVITS weights | [Model card and weights](https://huggingface.co/None1145/GPT-SoVITS-Rosmontis) |
| 10 | Arknights: Mon3tr | Model card languages are zh/en | GPT-SoVITS v3 SoVITS weight; availability of the GPT weight requires further verification | [Model card and weights](https://huggingface.co/None1145/GPT-SoVITS-Mon3tr) |
| 11 | Firefly | The model card explicitly says that only Chinese was tested | v2ProPlus GPT and SoVITS weights | [Model card and weights](https://huggingface.co/Waterwzy/GPT-SoVITS-firefly-finetuning) |
| 12 | Cyrene | The model card explicitly says that Mandarin studio recordings were used | v2Pro GPT and SoVITS weights | [Model card and weights](https://huggingface.co/ildyrasm/HSR-Cyrene-GPT-SoVITS) |
| 13 | Kokkoro | The dataset name explicitly identifies Chinese source audio | Multiple GPT-SoVITS v4 checkpoints | [Model card and weights](https://huggingface.co/yuier0721/Gpt-SoVITS_pcr-kokkoro_1.0) |
| 14 | Tang Yuge | The model card is tagged Chinese, anime, galgame, and character-voice | v2Pro GPT and SoVITS weights | [Model card and weights](https://huggingface.co/suyuan37/TangYuGe-GPT-SoVITS-v2pro) |
| 15 | Conan, Crayon Shin-chan, and Keroro (Korean dub) | The repository explicitly identifies Korean (`ko`) | Per-character GPT and SoVITS weights | [gahyunlee file tree](https://huggingface.co/gahyunlee/GPT-SoVITS-ko-character/tree/main) |
| 16 | Conan, Crayon Shin-chan, and Keroro (another Korean-dub collection) | The repository explicitly identifies Korean (`ko`) | Per-character GPT and SoVITS weights | [baliwalker file tree](https://huggingface.co/baliwalker/GPT-SoVITS-ko-character/tree/main) |
| 17 | `aris` (exact character not documented) | The name may refer to an anime-style game character, but the model card does not document its source or language | GPT and SoVITS weights | [File tree](https://huggingface.co/cueavyqwp/GPT-SoVITS-Models/tree/main) |
| 18 | Shorekeeper | *Wuthering Waves* character; training language not documented | GPT and SoVITS weights | [File tree](https://huggingface.co/chaliner/GPT_SoVITS-Shorekeeper/tree/main) |
| 19 | Sandrone | *Genshin Impact* character; the model card names only an AI-Hobbyist dataset and does not state the language | v2ProPlus GPT and SoVITS weights | [Model card and weights](https://huggingface.co/EarthlyEric6/Sandrone_gptsovits) |

## Typical exclusions from the main tables

- Official GPT-SoVITS base models, source code, WebUI packages, or inference bundles without character- or speaker-specific weights.
- Repositories containing only reference audio or datasets without usable GPT and SoVITS weights.
- Clearly Western animation, real people, streamers, political figures, commercial narration, or non-Japanese game characters.
- Repositories whose names and weight filenames are too abstract and whose model cards provide no character, work, language, or voice-source information to support responsible classification.

## Usage notes

1. GPT-SoVITS usually requires a paired GPT weight, commonly `.ckpt`, and SoVITS weight, commonly `.pth`. For archive-only repositories, inspect the archive before use to confirm that both are included.
2. The ability to synthesize Japanese does not mean that the target voice was trained from a Japanese voice actor. Cross-lingual inference may simply make a voice trained in another language speak Japanese.
3. For entries without a model card, audition repository samples or reference audio before deciding whether the source is a Japanese, Chinese, English, or Korean dub.
4. Character rights, voice or personality rights, performers' rights, game and anime asset copyright, and model licensing are distinct authorization layers. Commercial use requires particular care and often separate permission.
