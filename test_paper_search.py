import unittest

from paper_search import (
    abstract_from_inverted_index,
    build_journal_whitelist,
    is_excluded_publication,
    is_whitelisted_journal,
    is_topic_relevant,
    normalize_journal_name,
    parse_attachment2_foreign_journals,
    score_work,
    slugify_filename,
)


class PaperSearchTests(unittest.TestCase):
    def test_abstract_from_inverted_index_reconstructs_plain_text(self):
        index = {
            "credit": [0],
            "risk": [1],
            "prediction": [2],
            "uses": [3],
            "imbalanced": [4],
            "data": [5],
        }

        self.assertEqual(
            abstract_from_inverted_index(index),
            "credit risk prediction uses imbalanced data",
        )

    def test_normalize_journal_name_removes_case_spacing_and_punctuation(self):
        self.assertEqual(
            normalize_journal_name(" Journal of Banking & Finance "),
            normalize_journal_name("journal-of-banking and finance"),
        )

    def test_score_work_rewards_topic_fit_and_target_journal(self):
        work = {
            "title": "High-dimensional feature selection for corporate default prediction",
            "abstract": "We study imbalanced data in credit risk and financial distress prediction.",
            "journal": "Journal of Banking & Finance",
            "publication_year": 2024,
            "cited_by_count": 12,
            "doi": "https://doi.org/10.1234/example",
            "pdf_url": "https://example.org/paper.pdf",
        }

        scored = score_work(work)

        self.assertGreaterEqual(scored["score"], 10)
        self.assertEqual(scored["source_match"], "附件2/重点外文期刊")
        self.assertIn("high-dimensional", scored["matched_keywords"])
        self.assertIn("imbalanced", scored["matched_keywords"])

    def test_parse_attachment2_foreign_journals_from_compacted_pdf_text(self):
        text = (
            "1T11AmericanEconomicReview0002-82821944-7981"
            "2T12JournalofFinance0022-10821540-6261"
            "38T21JournalofBanking&Finance0378-42661872-6372"
        )

        journals = parse_attachment2_foreign_journals(text)

        self.assertIn("AmericanEconomicReview", journals)
        self.assertIn("JournalofFinance", journals)
        self.assertIn("JournalofBanking&Finance", journals)

    def test_whitelist_combines_attachment_ft50_and_utd24_names(self):
        whitelist = build_journal_whitelist(["JournalofBanking&Finance"])

        self.assertTrue(is_whitelisted_journal("Journal of Banking & Finance", whitelist))
        self.assertTrue(is_whitelisted_journal("Review of Financial Studies", whitelist))
        self.assertFalse(is_whitelisted_journal("IEEE Access", whitelist))

    def test_topic_relevance_requires_credit_or_default_theme(self):
        method_only = {
            "title": "Feature selection strategies for high-dimensional data",
            "abstract": "We compare SHAP and feature importance methods.",
        }
        credit_risk = {
            "title": "Feature selection for corporate default prediction",
            "abstract": "The model handles imbalanced credit risk observations.",
        }
        business_failure = {
            "title": "Extending business failure prediction models with textual data",
            "abstract": "The study forecasts bankruptcy and firm failure using machine learning.",
        }
        default_risk = {
            "title": "Performance of default-risk measures: the sample matters",
            "abstract": "We evaluate corporate default risk measures.",
        }
        nonperforming_loans = {
            "title": "Determinants of non-performing loans",
            "abstract": "The study models bank credit risk with neural networks.",
        }

        self.assertFalse(is_topic_relevant(method_only))
        self.assertTrue(is_topic_relevant(credit_risk))
        self.assertTrue(is_topic_relevant(business_failure))
        self.assertTrue(is_topic_relevant(default_risk))
        self.assertTrue(is_topic_relevant(nonperforming_loans))

    def test_excluded_publication_removes_review_articles(self):
        review = {
            "title": "Corporate default prediction using machine learning: literature review",
            "abstract": "This article surveys existing studies.",
        }

        self.assertTrue(is_excluded_publication(review))

    def test_slugify_filename_keeps_it_filesystem_safe(self):
        self.assertEqual(
            slugify_filename("A/B: Credit Risk? <2024>", "10.1000/abc"),
            "A_B_Credit_Risk_2024_10.1000_abc.pdf",
        )


if __name__ == "__main__":
    unittest.main()
