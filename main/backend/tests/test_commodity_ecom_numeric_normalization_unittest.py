from __future__ import annotations

import importlib
import sys
import types
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _ScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _FakeSession:
    def __init__(self, execute_result):
        self._execute_result = execute_result
        self.added = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *_args, **_kwargs):
        return self._execute_result

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


class _DummyQuery:
    def where(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self


class CommodityEcomNormalizationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        extraction_path = Path(__file__).resolve().parents[1] / "app" / "services" / "extraction"
        cls._orig_modules = {
            "app.models.base": sys.modules.get("app.models.base"),
            "app.models.entities": sys.modules.get("app.models.entities"),
            "app.services.extraction": sys.modules.get("app.services.extraction"),
            "app.services.ingest.adapters": sys.modules.get("app.services.ingest.adapters"),
            "app.services.ingest.adapters.http_utils": sys.modules.get("app.services.ingest.adapters.http_utils"),
        }

        base_stub = types.ModuleType("app.models.base")
        base_stub.SessionLocal = lambda: None

        entities_stub = types.ModuleType("app.models.entities")

        class _Field:
            def __eq__(self, _other):
                return self

            def asc(self):
                return self

        class _Entity:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        class _MarketMetricPoint(_Entity):
            metric_key = _Field()
            date = _Field()
            source_uri = _Field()

        class _Product(_Entity):
            enabled = _Field()
            id = _Field()

        class _PriceObservation(_Entity):
            pass

        entities_stub.MarketMetricPoint = _MarketMetricPoint
        entities_stub.Product = _Product
        entities_stub.PriceObservation = _PriceObservation
        entities_stub.EtlJobRun = _Entity

        extraction_stub = types.ModuleType("app.services.extraction")
        extraction_stub.__path__ = [str(extraction_path)]
        adapters_stub = types.ModuleType("app.services.ingest.adapters")
        adapters_stub.__path__ = []
        http_utils_stub = types.ModuleType("app.services.ingest.adapters.http_utils")
        http_utils_stub.fetch_html = lambda _url: ("", "utf-8")

        sys.modules["app.models.base"] = base_stub
        sys.modules["app.models.entities"] = entities_stub
        sys.modules["app.services.extraction"] = extraction_stub
        sys.modules["app.services.ingest.adapters"] = adapters_stub
        sys.modules["app.services.ingest.adapters.http_utils"] = http_utils_stub

        cls._commodity_module = importlib.import_module("app.services.ingest.commodity")
        cls._ecom_module = importlib.import_module("app.services.ingest.ecom")
        cls._numeric_general_module = importlib.import_module("app.services.extraction.numeric_general")
        cls._entities_stub = entities_stub

    @classmethod
    def tearDownClass(cls):
        for module_name, module_obj in cls._orig_modules.items():
            if module_obj is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = module_obj

    def test_commodity_ingest_sets_unit_and_currency(self):
        fake_session = _FakeSession(_ScalarOneResult(None))
        rows = [{"Date": "2026-02-01", "Close": "123.45"}]

        with (
            patch("app.services.ingest.commodity.start_job", return_value="job-1"),
            patch("app.services.ingest.commodity.complete_job"),
            patch("app.services.ingest.commodity.fail_job"),
            patch("app.services.ingest.commodity._fetch_stooq_rows", return_value=rows),
            patch("app.services.ingest.commodity.SessionLocal", return_value=fake_session),
            patch("app.services.ingest.commodity.select", return_value=_DummyQuery()),
        ):
            result = self._commodity_module.ingest_commodity_metrics(
                symbols={"commodity.test": "foo"},
                limit=1,
            )

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["skipped"], 0)
        self.assertTrue(fake_session.committed)
        point = fake_session.added[0]
        self.assertEqual(point.metric_key, "commodity.test")
        self.assertEqual(point.unit, "price")
        self.assertEqual(point.currency, "USD")
        self.assertIn("numeric_quality", point.extra)
        self.assertEqual(point.extra["numeric_quality"]["source"], "ingest_commodity_normalize")

    def test_ecom_collect_uses_extracted_currency_first(self):
        fake_session = _FakeSession(
            _ScalarsResult(
                [
                    self._entities_stub.Product(
                        id=101,
                        name="demo",
                        source_uri="https://example.test/p/1",
                        currency="CNY",
                        enabled=True,
                    )
                ]
            )
        )

        with (
            patch("app.services.ingest.ecom.start_job", return_value="job-2"),
            patch("app.services.ingest.ecom.complete_job"),
            patch("app.services.ingest.ecom.fail_job"),
            patch("app.services.ingest.ecom.SessionLocal", return_value=fake_session),
            patch("app.services.ingest.ecom.fetch_html", return_value=("<html/>", "utf-8")),
            patch("app.services.ingest.ecom.select", return_value=_DummyQuery()),
            patch(
                "app.services.ingest.ecom._extract_price_from_html",
                return_value=(Decimal("19.90"), "USD", "InStock"),
            ),
        ):
            result = self._ecom_module.collect_ecom_price_observations(limit=1)

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["skipped"], 0)
        self.assertTrue(fake_session.committed)
        obs = fake_session.added[0]
        self.assertEqual(obs.price, Decimal("19.90"))
        self.assertEqual(obs.currency, "USD")
        self.assertEqual(obs.availability, "InStock")
        self.assertIn("numeric_quality", obs.extra)
        self.assertEqual(obs.extra["numeric_quality"]["source"], "ingest_ecom_normalize")

    def test_ecom_collect_falls_back_to_product_currency(self):
        fake_session = _FakeSession(
            _ScalarsResult(
                [
                    self._entities_stub.Product(
                        id=202,
                        name="demo2",
                        source_uri="https://example.test/p/2",
                        currency="EUR",
                        enabled=True,
                    )
                ]
            )
        )

        with (
            patch("app.services.ingest.ecom.start_job", return_value="job-3"),
            patch("app.services.ingest.ecom.complete_job"),
            patch("app.services.ingest.ecom.fail_job"),
            patch("app.services.ingest.ecom.SessionLocal", return_value=fake_session),
            patch("app.services.ingest.ecom.fetch_html", return_value=("<html/>", "utf-8")),
            patch("app.services.ingest.ecom.select", return_value=_DummyQuery()),
            patch(
                "app.services.ingest.ecom._extract_price_from_html",
                return_value=(Decimal("88.00"), None, None),
            ),
        ):
            result = self._ecom_module.collect_ecom_price_observations(limit=1)

        self.assertEqual(result["inserted"], 1)
        obs = fake_session.added[0]
        self.assertEqual(obs.currency, "EUR")

    def test_ecom_html_jsonld_price_parsing(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Product","offers":{"price":"39.5","priceCurrency":"USD","availability":"InStock"}}
        </script>
        """
        price, currency, availability = self._ecom_module._extract_price_from_html(html)
        self.assertEqual(price, Decimal("39.5"))
        self.assertEqual(currency, "USD")
        self.assertEqual(availability, "InStock")

    def test_numeric_general_outputs_unit_currency_and_quality(self):
        result = self._numeric_general_module.extract_numeric_general("约 ¥1.2万", default_currency="USD")
        self.assertTrue(result["parsed"])
        self.assertEqual(result["normalized_unit"], "value")
        self.assertEqual(result["currency"], "CNY")
        self.assertEqual(result["value"], 12000.0)
        self.assertEqual(result["quality_score"], 95.0)
        self.assertEqual(result["error_code"], self._numeric_general_module.GENERAL_NUMERIC_OK)

    def test_numeric_general_percent_ratio_quality(self):
        result = self._numeric_general_module.extract_numeric_general("0.25", expect_percent=True)
        self.assertTrue(result["parsed"])
        self.assertEqual(result["normalized_unit"], "percent")
        self.assertEqual(result["value"], 25.0)
        self.assertEqual(result["quality_score"], 90.0)
        self.assertEqual(result["error_code"], self._numeric_general_module.GENERAL_NUMERIC_OK)

    def test_commodity_low_quality_is_skipped(self):
        fake_session = _FakeSession(_ScalarOneResult(None))
        rows = [{"Date": "2026-02-01", "Close": "123.45"}]

        with (
            patch("app.services.ingest.commodity.start_job", return_value="job-4"),
            patch("app.services.ingest.commodity.complete_job"),
            patch("app.services.ingest.commodity.fail_job"),
            patch("app.services.ingest.commodity._fetch_stooq_rows", return_value=rows),
            patch("app.services.ingest.commodity.SessionLocal", return_value=fake_session),
            patch("app.services.ingest.commodity.select", return_value=_DummyQuery()),
            patch(
                "app.services.ingest.commodity.extract_numeric_general",
                return_value={
                    "parsed": True,
                    "value": 123.45,
                    "quality_score": 10.0,
                    "error_code": "OK",
                    "meta": {},
                },
            ),
        ):
            result = self._commodity_module.ingest_commodity_metrics(
                symbols={"commodity.test": "foo"},
                limit=1,
            )

        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 1)

    def test_commodity_update_merges_existing_numeric_quality(self):
        existing = self._entities_stub.MarketMetricPoint(
            metric_key="commodity.test",
            date=date.fromisoformat("2026-02-01"),
            source_uri="https://stooq.com/q/d/l/?s=foo&i=d",
            value=Decimal("100.0"),
            extra={"numeric_quality": {"source": "legacy", "quality_score": 80.0}},
        )
        fake_session = _FakeSession(_ScalarOneResult(existing))
        rows = [{"Date": "2026-02-01", "Close": "123.45"}]

        with (
            patch("app.services.ingest.commodity.start_job", return_value="job-6"),
            patch("app.services.ingest.commodity.complete_job"),
            patch("app.services.ingest.commodity.fail_job"),
            patch("app.services.ingest.commodity._fetch_stooq_rows", return_value=rows),
            patch("app.services.ingest.commodity.SessionLocal", return_value=fake_session),
            patch("app.services.ingest.commodity.select", return_value=_DummyQuery()),
        ):
            result = self._commodity_module.ingest_commodity_metrics(
                symbols={"commodity.test": "foo"},
                limit=1,
            )

        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(existing.value, Decimal("123.45"))
        self.assertIn("numeric_quality", existing.extra)
        self.assertIn("source", existing.extra["numeric_quality"])
        self.assertIn("ingest", existing.extra["numeric_quality"])
        self.assertEqual(existing.extra["numeric_quality"]["ingest"]["source"], "ingest_commodity_normalize")

    def test_ecom_low_quality_is_skipped(self):
        fake_session = _FakeSession(
            _ScalarsResult(
                [
                    self._entities_stub.Product(
                        id=303,
                        name="demo3",
                        source_uri="https://example.test/p/3",
                        currency="USD",
                        enabled=True,
                    )
                ]
            )
        )

        with (
            patch("app.services.ingest.ecom.start_job", return_value="job-5"),
            patch("app.services.ingest.ecom.complete_job"),
            patch("app.services.ingest.ecom.fail_job"),
            patch("app.services.ingest.ecom.SessionLocal", return_value=fake_session),
            patch("app.services.ingest.ecom.fetch_html", return_value=("<html/>", "utf-8")),
            patch("app.services.ingest.ecom.select", return_value=_DummyQuery()),
            patch(
                "app.services.ingest.ecom._extract_price_from_html",
                return_value=(Decimal("19.90"), "USD", "InStock"),
            ),
            patch(
                "app.services.ingest.ecom.extract_numeric_general",
                return_value={
                    "parsed": True,
                    "value": 19.90,
                    "quality_score": 10.0,
                    "error_code": "OK",
                    "meta": {},
                },
            ),
        ):
            result = self._ecom_module.collect_ecom_price_observations(limit=1)

        self.assertEqual(result["inserted"], 0)
        self.assertEqual(result["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
