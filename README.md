# JevTex

TeXの「式1 → 式2」をJevで判定し、変形後の式をPDF上で誤りは赤、判断保留は黄色で表示するローカルWebアプリ。

## 起動

このMacではプロジェクト内の `.tools/texlive` にBasicTeXと日本語パッケージを準備済みです。システムのTeX設定やPATHは変更していません。

```sh
cd JevTex
uv sync --frozen
npm ci --ignore-scripts
uv run python -m jevtex
```

[http://127.0.0.1:8765](http://127.0.0.1:8765) を開きます。起動コマンドはlocalhostだけにバインドします。停止はCtrl+Cです。

Jevで判定する場合は、**起動前に同じターミナルで**環境変数を設定します。macOSのzshなら次のコマンドでキーを画面・シェル履歴に表示せず入力できます。

```zsh
read -rs 'TYPESAFE_API_KEY?TypeSafe API key: '; echo
export TYPESAFE_API_KEY
uv run python -m jevtex
```

キーはTypeSafe公式APIへの認証にだけ使用します。ブラウザ入力欄は設けておらず、ソース・ログ・結果JSON・PDF・TeX子プロセスには含めません。`.env.example` は設定名の例で、`.env`の自動読込はしません。キーなしでもTeX取り込み・PDF閲覧・比較ペア編集はできます。

別のMacでTeX未導入の場合は `bash scripts/setup_tex.sh` を実行してください。公式Homebrew caskのBasicTeXを `.tools/texlive` に展開し、日本語用のluatexja・HaranoAjiを追加します。管理者権限不要で、このディレクトリはGit対象外です。既存のLuaLaTeXとSyncTeXはPATHまたは `/Library/TeX/texbin` からも検出します。Python 3.12–3.14、uv、Node.js 22以降が必要です。

## 使い方

1. 「TeXファイルを開く」からUTF-8の単一TeX（1MB以下）を読み込みます。
2. 自動候補の式1・式2を確認します。別々の定義は除外し、必要なら追加・変更します。
3. 共通の前提条件と、各ペアの「参照式と送信する周辺説明」を確認します。
4. 「Jevで判定する」を押すと、選択した式・定義・前提・周辺説明をTypeSafe公式APIへ送ります。
5. 判定・確率を確認し、「PDFへ」で該当箇所に移動します。ハイライトの表示を切り替え、別名の注釈付きPDFと結果JSONを保存できます。

画面と保存PDFは、誤りを赤、判断保留（確率不足を含む）を黄色で表示します。同じ式に両方の判定がある場合は赤を優先します。通信失敗と位置未取得の式には色を付けません。

入力ファイル名、文書タイトル、未選択の全文、正解データはAPIに送りません。数式自体や周辺説明に機密情報がある場合は送信対象になります。数式・前提の自動修正は行いません。

## 表示言語

右上の言語メニューで日本語・英語を切り替えます。選択はブラウザに保存され、未選択時は日本語です。切替時に文書・比較ペア・入力済みの前提・判定結果・PDF倍率は保持します。文書本文、数式、ユーザーの入力、APIの生データは翻訳しません。

翻訳は `static/locales.json` に集約しています。言語を追加する場合は `ja` を複製し、言語コードをキーとして `name` にその言語の名称、`messages` に翻訳を設定します。メニューには自動で追加され、画面側の編集は不要です。`{pairs}` などのプレースホルダーは保持してください。翻訳が欠けた項目は日本語に戻ります。

`server.*` は既存API・保存結果の日本語メッセージを画面上で翻訳する項目です。サーバーの警告やエラーを変更した場合は、日本語側の対応文言も更新してください。未知の診断メッセージは原文のまま表示します。

```sh
node tests/test_i18n.mjs
```

## 判定とテストデータ

Jevの`Choice`は `correct / incorrect / uncertain` の3択です。選択確率が暫定閾値0.8未満なら画面では判断保留とし、生の選択・確率・confidenceも表示します。confidenceと選択確率は別の値です。モデルは`jev-1.13.0`に固定し、`JEV_MODEL`環境変数で変更できます。通信失敗は判断保留とは別に表示します。429・529・503だけ上限2回の再試行、各リクエストのタイムアウトは30秒です。

評価単位は**局所的な式変形**です。式1に以前の誤りがあっても、その式を出発点とした次の変形が正しければcorrectです。Jevは証明器ではなく、数学的な正しさを保証しません。

| ファイル | 内容 |
| --- | --- |
| `examples/laplacian_correct.tex` | 日本語の説明付き2次元極座標ラプラシアン。12式、6比較ペア、2ページ。 |
| `examples/laplacian_mistake.tex` | e10→e11で `f_r/r` を脱落。e11→e12は欠落を引き継ぐが、くくり出しは正しい。 |
| `examples/expected.json` | ペアごとの期待判定・説明と共通の前提。評価スクリプト専用でJevへ送信しない。 |
| `examples/matrix_calculus_mistake.tex` | 高難度：行列指数・二重交換子・対数行列式の二次変分。11式、8比較ペア、新しい誤り3か所。ファイル選択から読み込む。 |
| `examples/matrix_calculus_answers.md` / `matrix_calculus_expected.json` | 高難度サンプルの誤りの位置・正しい式・厳密な反例と期待判定。解答はJevへ送信しない。 |

高難度サンプルの正解は `tests/test_matrix_sample.py` で独立したSymPy計算により確認する。実Jevによる判定は未実施。下記のPDF作成・実API評価スクリプトは従来のラプラシアン2文書を対象とする。

```sh
# 模擬API、抽出、独立したSymPy計算、境界条件
uv run python -m unittest discover -s tests -v
node tests/test_highlights.mjs

# 実TeXコンパイル、SyncTeX、PDF注釈とAPI全体も検証（Jev応答は模擬）
JEVTEX_INTEGRATION=1 uv run python -m unittest discover -s tests -v

# サンプルPDFと、正解データで赤い位置を示すデモPDFを作成
uv run python -m scripts.build_examples

# 実際のJevによる精度評価：キーが必要・12ペア分のAPI呼び出し
uv run python -m scripts.evaluate
```

実API評価は `output/evaluation.json` に検出率・誤検出数・保留数・通信失敗数・全ペアの結果を保存します。期待判定と不一致なら終了コード1、キー未設定なら未実施として終了コード2です。正解ラベルはAPI入力から分離します。2文書・意図的な誤り1件という小さなデータのため、結果を一般的な数学能力とみなさないでください。

`output/pdf/mistake/overlay-demo.pdf` は**正解データによる表示デモで、Jevによる検出結果ではありません**。同名のJSONにも `oracle-demo-NOT-Jev` と記録します。模擬テストの成功と実モデル精度は別に報告します。

## 対応範囲と保存

- 対応：文書直下の`equation`、`equation*`、`align`、`align*`、`\[...\]`。align内の最上位の改行を区切り、matrix等の内部改行は保持します。省略された左辺は前のalign行から補います。
- 比較候補は同じ節の隣接式。参照式は式2より前の式を選びます。独自マクロ展開、複数ファイル、画像、PDF単体、`gather`等には未対応で、警告・入力エラーを表示します。
- LuaLaTeXを2回実行し、SyncTeXで環境末尾の正確な記録を照合します。amsmathのalignは全行が環境末尾に記録されるため、外側の表示ボックスを順番に対応付けます。ボックス数が行数と一致しない場合は「位置未取得」にします。数式中の個別の記号位置までは判定しません。
- 元のTeXは変更せず `.jevtex/<文書ID>/document.tex` にコピーします。PDF、SyncTeX、結果、ログも同じ作業フォルダへ保存します。生成物とアップロード内容はGit対象外です。文書ごとに保存され、自動削除はしません。不要になった作業フォルダはアプリ停止後に手動で削除できます。
- 本人が管理するTeXをローカルで扱う用途です。shell escapeは禁止し、環境変数を絞り、コンパイルは各90秒で打ち切ります。任意のLua/TeXを安全に実行できるOSサンドボックスではありません。公開サーバーとして使用しないでください。

フロントエンドはPDF.jsをローカル配信します。CDN、分析ツール、外部フォントは使用しません。Gitにはコード・TeX・正解データ・ロックファイルだけを含め、リモートリポジトリは設定しません。

## 内部API

POSTは同一originと `X-JevTex-Client: 1` ヘッダーを要求します。認証キーをブラウザから受け取るAPIはありません。

| API | 入出力 |
| --- | --- |
| `GET /api/status` | キー設定の有無、モデル、閾値、TeXツール有無。キー値は返さない。 |
| `POST /api/documents` | `{name, source}` → 文書ID・抽出式・候補・位置・警告。コンパイル失敗時も抽出結果を返す。 |
| `POST /api/documents/{id}/check` | `{pairs:[{before, after, context_ids}], assumptions}` → 判定結果。1回最大50ペア。 |
| `GET /api/documents/{id}/pdf` | 原PDF。`?annotated=true`で注釈付きの別名PDF。 |
| `GET /api/documents/{id}/results` | 結果JSON。式ID・ソース位置・確率・モデル・PDF位置を含む。 |

PDF位置は1始まりのページ番号と、左下原点・PDF point単位の`rect=[x0,y0,x1,y1]`です。PDF.jsのviewportで画面座標に変換し、保存PDFにも同じ矩形を使います。

仕様の出典：[TypeSafe API](https://docs.typesafe.ai/api)、[既知の弱点](https://docs.typesafe.ai/model-jaggedness/jev-1.13)、[PDF.js](https://mozilla.github.io/pdf.js/examples/)、[pypdf注釈](https://pypdf.readthedocs.io/en/stable/user/adding-pdf-annotations.html)。

## 実装時の検証記録（2026-09-21）

統合テストを含む7件が成功。両サンプルは2ページでコンパイルでき、12式すべてのPDF位置を取得しました。SymPyによる微分計算、PDF再読込、元PDFの不変性、認証失敗・タイムアウト・低確率・不正応答・秘密情報の非伝播を検証しています。ブラウザではペア変更、PDF表示、模擬応答による式11への赤い表示、150%への拡大、表示切替、該当箇所への移動を確認しました。

実API用キーは未設定のため、Jevによる実際の検出精度は未検証です。赤い表示の検証は模擬応答・正解データを使用しており、Jevが誤りを検出したという実績には含めません。
