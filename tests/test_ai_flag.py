import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_flag  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "config.yaml"), encoding="utf-8"))["ai"]


def detect(desc, title="Android Developer"):
    return ai_flag.detect(title, desc, CFG)


@pytest.mark.parametrize("text", [
    "LLM", "GPT-4 integration", "OpenAI API", "Anthropic", "Claude", "Gemini Nano", "GenAI", "Generative AI",
    "chatbot", "AI assistant", "RAG pipelines", "machine learning", "uczenie maszynowe", "ML Kit", "TensorFlow Lite",
    "TFLite", "LiteRT", "MediaPipe", "on-device ML", "Computer Vision", "sztuczna inteligencja", "Artificial Intelligence",
    "AI", "we use A.I.-powered features and AI/ML", "LLMs",
])
def test_product_keywords(text):
    assert detect(text).startswith("produkt")


@pytest.mark.parametrize("text", [
    "GitHub Copilot", "Cursor", "Claude Code", "AI tools", "AI-assisted development", "agentic workflows",
    "prompt engineering", "coding agents", "AI agents in software development", "agents for development",
])
def test_workflow_keywords(text):
    assert detect(text).startswith("workflow")


def test_both_categories_and_at_most_three_words():
    assert detect("Experience with LLM, GPT and OpenAI; we use Copilot and Cursor daily") == "produkt + workflow (llm, copilot, gpt)"
    assert detect("copilot, cursor, claude code, ai tools") == "workflow (copilot, cursor, claude code)"
    assert detect("we use agentic coding and an llm") == "produkt + workflow (llm, agentic)"
    assert detect("RAG") == "produkt (rag)"


def test_title_counts_too():
    assert ai_flag.detect("Android Developer (AI)", "", CFG) == "produkt (ai)"


@pytest.mark.parametrize("text", [
    "", "Android Developer", "said, paid, maid, aim, rail, Kotlin", "email", "agent smith", "Developer agent", "storage",
    "fragment, garage, leverage", "kotlinx.coroutines", "paint", "Taiwan",
])
def test_no_false_positives_inside_words(text):
    assert detect(text) == ""


def test_bare_ai_detection_for_review():
    assert ai_flag.only_bare_ai(detect("AI features"), "T", "AI features", CFG)
    assert not ai_flag.only_bare_ai(detect("AI and llm"), "T", "AI and llm", CFG)
