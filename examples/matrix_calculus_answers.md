# 非可換行列の微分と二次変分：解答

対象は `matrix_calculus_mistake.tex`。11式・8比較ペアで、**新しい誤りを3か所**入れている。TeXの式番号とアプリの式ID（e1～e11）は対応する。この解答と期待判定JSONはJevへ送らない。

行列指数のフレシェ微分、共役作用の二重交換子、対数行列式の二次変分を扱う。スカラーでは正しい整理を行列に誤って適用する問題と、符号の誤りを組み合わせた。

## 1. 式(2) → 式(3)：Hを勝手に右端へ移動

一般に行列積は非可換なので、$X^kHX^{n-1-k}$ を $X^{n-1}H$ に置き換えられない。$XH=HX$ ならこの整理は正しいが、その仮定はない。

正しい一般式は式(2)、または次の積分表示である。

$$D(\exp)_X[H]=\int_0^1 e^{(1-s)X}H e^{sX}\,ds.$$

反例として

$$X=\begin{pmatrix}1&0\\0&0\end{pmatrix},\qquad H=\begin{pmatrix}0&1\\0&0\end{pmatrix}$$

をとる。$(X+tH)^2=X+tH$ より $e^{X+tH}=I+(e-1)(X+tH)$。したがって実際の微分は $(e-1)H$ だが、式(4)は $eH$ を与え、一致しない。

**式(3) → 式(4)の再総和は局所的には正しい。** 式(4)という結論は一般には誤りでも、その段階で新しい誤りは発生していない。

## 2. 式(5) → 式(6)：最後のBA²の符号

正しく展開すると

$$[A,[A,B]]=A(AB-BA)-(AB-BA)A=A^2B-2ABA+BA^2.$$

式(6)では最後を $-BA^2$ にしている。式(6)のその項と、式(7)の対応する項を $+BA^2$ にすれば正しい。

反例として

$$A=\begin{pmatrix}1&0\\0&2\end{pmatrix},\qquad B=\begin{pmatrix}0&1\\0&0\end{pmatrix}$$

をとると、$C(t)=e^{-t}B$ なので $C''(0)=B$。正しい展開も $B-4B+4B=B$ だが、サンプルの式(7)は $B-4B-4B=-7B$ を与える。

**式(6) → 式(7)は、解析関数のテイラー係数から二階微分を読む操作として正しい。** 先行する符号の誤りだけを継承している。

## 3. 式(9) → 式(10)：トレースの巡回性の誤用

トレースでは因子の列を巡回移動できるが、任意の二つの因子を交換できるわけではない。

$$\operatorname{tr}(X^{-1}KX^{-1}H)=\operatorname{tr}(X^{-1}HX^{-1}K)$$

は正しい。しかし一般に $\operatorname{tr}(X^{-2}KH)$ とは等しくない。正しい二次微分は式(9)のままであり、同一方向なら

$$D^2\Phi_X[H,H]=-\operatorname{tr}(X^{-1}HX^{-1}H).$$

反例として

$$X=\begin{pmatrix}1&0\\0&2\end{pmatrix},\qquad H=K=\begin{pmatrix}0&1\\1&0\end{pmatrix}$$

をとる。$X$ は正定値、$H,K$ は対称なので前提を満たす。
$\det(X+tH)=2-t^2$ から直接計算すると

$$\left.\frac{d^2}{dt^2}\log(2-t^2)\right|_{t=0}=-1.$$

式(9)も $-1$ を与えるが、式(10)、式(11)は $-5/4$ を与える。

**式(10) → 式(11)の $K=H$ という代入自体は正しい。** 式(11)だけを再度「新しい誤り」と判定しないことが、このデータの評価ポイントになる。

## 期待する局所判定

| 比較 | 期待判定 | 内容 |
| --- | --- | --- |
| e1 → e2 | correct | 積の微分 |
| e2 → e3 | incorrect | 非可換な因子の並べ替え |
| e3 → e4 | correct | 再総和。誤りを継承 |
| e5 → e6 | incorrect | 二重交換子の符号 |
| e6 → e7 | correct | テイラー係数。誤りを継承 |
| e8 → e9 | correct | 逆行列の微分 |
| e9 → e10 | incorrect | トレース内の因子の交換 |
| e10 → e11 | correct | 同一方向への制限。誤りを継承 |

各節は独立なので、e4 → e5、e7 → e8は比較しない。

## 読み込みと検証

アプリのファイル選択から `examples/matrix_calculus_mistake.tex` を読み込む。上記8ペアが自動抽出される。共通の前提欄には `matrix_calculus_expected.json` の `assumptions` の値だけをコピーできる。`expected` と `explanation` は解答なので入力しない。

`tests/test_matrix_sample.py` はSymPyによる厳密計算で3つの反例、正しい一般展開、後続の変形を検証し、TeXの式・ペアと期待データの対応も確認する。これはJevの検出精度の検証ではなく、このサンプルの数学的な正解の確認である。新サンプルの実Jev評価は未実施。

既存の `scripts.evaluate` はラプラシアンの2文書を対象とする。この追加サンプルは現時点ではアプリから判定する。

参考：行列指数の微分の積分表示は [Nick Higham, What Is a Fréchet Derivative?](https://nhigham.com/2020/06/23/what-is-a-frechet-derivative/)、逆行列と行列式の微分は [MIT 18.S096, Lecture Notes and Readings](https://ocw.mit.edu/courses/18-s096-matrix-calculus-for-machine-learning-and-beyond-january-iap-2023/pages/lecture-notes-and-readings/) を参照。上の反例はこのサンプル用に独立計算した。
