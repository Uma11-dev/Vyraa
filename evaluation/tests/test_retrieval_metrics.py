import unittest

from evaluation.metrics.retrieval_metrics import (
    aggregate_metric_rows,
    evaluate_retrieval_case,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


class RetrievalMetricTests(unittest.TestCase):
    def test_precision_at_k(self):
        self.assertAlmostEqual(precision_at_k(["a", "b", "c"], ["b", "c"], 3), 2 / 3)

    def test_recall_at_k(self):
        self.assertAlmostEqual(recall_at_k(["a", "b", "c"], ["b", "c", "d"], 2), 1 / 3)

    def test_reciprocal_rank(self):
        self.assertAlmostEqual(reciprocal_rank(["x", "b", "a"], ["a", "b"]), 0.5)

    def test_ndcg_perfect_ranking(self):
        self.assertAlmostEqual(ndcg_at_k(["a", "b"], {"a": 3, "b": 1}, 2), 1.0)

    def test_no_labels_returns_none(self):
        metrics = evaluate_retrieval_case(["a", "b"], relevant_ids=[])
        self.assertIsNone(metrics["mrr"])
        self.assertIsNone(metrics["precision_at_5"])
        self.assertIsNone(metrics["recall_at_5"])

    def test_duplicate_retrieval_ids_are_deduplicated(self):
        self.assertAlmostEqual(precision_at_k(["a", "a", "b"], ["a", "b"], 2), 1.0)

    def test_invalid_k_rejected(self):
        with self.assertRaises(ValueError):
            precision_at_k(["a"], ["a"], 0)

    def test_aggregate_reports_coverage(self):
        rows = [
            evaluate_retrieval_case(["a", "b"], ["a"]),
            evaluate_retrieval_case(["x", "y"], []),
        ]
        summary = aggregate_metric_rows(rows)
        self.assertEqual(summary["total_cases"], 2)
        self.assertEqual(summary["scored_cases"], 1)
        self.assertEqual(summary["mrr_coverage"], 0.5)


if __name__ == "__main__":
    unittest.main()
