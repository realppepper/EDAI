"""
학습된 FLAN-T5 로 구조 후보를 만든다 (이 컴퓨터 CPU 에서. 학습은 Colab 에서 한 번만 한다).

입력: data/train/<부품>.json 의 입력 문장 (spec_from_hkg.py 가 만듦)
결과: data/train/<부품>_candidates.json  (select_structure.py 가 읽는다)

후보 만드는 법은 Colab 노트북(colab/flan_t5_structure.ipynb) 8번 셀과 같다.
    가장 그럴듯한 답 10개(빔 탐색) + 조금씩 무작위로 바꾼 답 30개, 같은 답은 하나로
후보마다 규칙 검사 결과(problems)와 학습 데이터에 있던 구조인지(in_train)를 적는다.

모델: models/flan_t5_structure (구글 드라이브 2026_2/flan_t5_structure 를 내려받은 폴더, git 에 올리지 않음)
    경로는 환경변수 EDAI_MODEL_DIR 로 바꿀 수 있다.

사용법 (WSL, 프로젝트 폴더에서):
    ~/.venvs/edai/bin/python generate_candidates.py lm358
"""

import json
import os
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

import select_structure

HERE = Path(__file__).resolve().parent
TRAIN_DIR = HERE / "data" / "train"
MODEL_DIR = Path(os.environ.get("EDAI_MODEL_DIR", HERE / "models" / "flan_t5_structure"))
MODEL_INFO = TRAIN_DIR / "model_eval.json"   # 모델 이름, 학습 에폭, 검증 결과 (Colab 학습 때 기록)
MAX_INPUT_TOKENS = 256
MAX_TARGET_TOKENS = 768
CANDIDATES_BEAM = 10
CANDIDATES_SAMPLED = 30
SAMPLE_BATCH = 10
TOP_P = 0.95
TEMPERATURE = 0.8
SEED = 7


def normalize(text: str) -> str:
    return " ".join(text.split())


def problems(text: str) -> list:
    """select_structure 와 같은 규칙 검사. 빈 목록이면 통과."""
    try:
        table = select_structure.to_table(text)
    except ValueError as error:
        return [f"형식: {error}"]
    return select_structure.rule_problems(table)


def main() -> None:
    part = sys.argv[1]
    torch.manual_seed(SEED)
    sentence = json.loads((TRAIN_DIR / f"{part}.json").read_text(encoding="utf-8"))["input"]
    train_targets = {normalize(json.loads(line)["target"])
                     for line in (TRAIN_DIR / "train.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()}
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    # Colab(transformers 5)이 저장한 설정은 tie_word_embeddings=true지만 lm_head는 따로 학습돼 있다.
    # 4.x에서 그대로 읽으면 lm_head를 입력 임베딩으로 덮어써서 엉뚱한 글자가 나오므로 묶지 않게 한다.
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_DIR, tie_word_embeddings=False).eval()
    encoded = tokenizer([sentence], return_tensors="pt", truncation=True, max_length=MAX_INPUT_TOKENS)
    started = time.time()

    def generate(**kwargs) -> list:
        with torch.no_grad():
            out = model.generate(**encoded, max_new_tokens=MAX_TARGET_TOKENS, **kwargs)
        return [normalize(t) for t in tokenizer.batch_decode(out, skip_special_tokens=True)]

    texts = [("beam", t) for t in generate(num_beams=CANDIDATES_BEAM, num_return_sequences=CANDIDATES_BEAM)]
    print(f"  빔 탐색 {CANDIDATES_BEAM}개: {time.time() - started:.0f} s", flush=True)
    for _ in range(CANDIDATES_SAMPLED // SAMPLE_BATCH):
        texts += [("sample", t) for t in generate(do_sample=True, top_p=TOP_P, temperature=TEMPERATURE,
                                                  num_return_sequences=SAMPLE_BATCH)]
        print(f"  무작위 {len(texts) - CANDIDATES_BEAM}개: {time.time() - started:.0f} s", flush=True)
    candidates = []
    for how, text in texts:
        if any(c["table"] == text for c in candidates):
            continue
        candidates.append({"how": how, "table": text, "problems": problems(text), "in_train": text in train_targets})
    info = json.loads(MODEL_INFO.read_text(encoding="utf-8"))
    result = dict(info, input=sentence, generated={"beam": CANDIDATES_BEAM, "sample": CANDIDATES_SAMPLED},
                  candidates=candidates)
    out = TRAIN_DIR / f"{part}_candidates.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    passed = [c for c in candidates if not c["problems"]]
    print(f"모델이 쓴 글 {len(texts)}개 -> 서로 다른 후보 {len(candidates)}개, 규칙 통과 {len(passed)}개, "
          f"그중 학습 데이터에 없던 구조 {sum(not c['in_train'] for c in passed)}개 -> {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
