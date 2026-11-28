# OMZU

An assistant for Uzbek with a small GPT model trained on Kaggle. It is not deployed.

## Features

- A 32,000-token BPE tokenizer trained on cleaned Uzbek and English text
- A GPT pretrained on Kaggle with two T4 GPUs, then fine-tuned on questions and answers
- Facts come from a search over 231,000 Uzbek Wikipedia articles; live data such as weather and exchange rates comes from tools
- A guard that makes the assistant say it does not know
- A 52-question test run on five configurations

## Stack

Python, PyTorch, FastAPI, SQLite FTS5, React 19, TypeScript, Tailwind CSS

## Structure

```
uzllm/      model, tokenizer, search, tools and server
uztts/      text preparation for speech
scripts/    data, tokenizer, training and test scripts
kaggle/     training kernels
webapp/     chat interface
tests/      unit tests
```

## Run

Python 3 and Node.js are required. Model weights and data are not in this repository.

```
python -m uzllm.server
```

Open http://127.0.0.1:8000

Interface:

```
cd webapp
npm install
npm run dev
```

Tests:

```
python -m pytest tests
```

## Data

FineWeb-2 and FineWeb-Edu (ODC-By), Wikipedia (CC BY-SA), Aya (Apache 2.0)
