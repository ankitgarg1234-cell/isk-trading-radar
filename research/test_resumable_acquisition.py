import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import Mock
from research.resumable_acquisition import ResumableAcquisition
from research.spgm_sources import ROOT


class AcquisitionTests(unittest.TestCase):
    def quota(self):
        return dict(quota_date_is_current=True,api_requests_date=datetime.now(timezone.utc).date().isoformat(),reported_remaining_units=1)

    def test_cached_resume_does_not_repeat_request(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            client=Mock();client.get.return_value=[{'date':'2023-01-01','close':100}]
            a=ResumableAcquisition(temp,quota=self.quota(),history_entitled=True,max_units=1,client=client)
            first=a.get('eod','FIXTURE.US',mapping_verified=True)
            b=ResumableAcquisition(temp,quota={},history_entitled=False,max_units=0,client=client)
            self.assertEqual(b.get('eod','FIXTURE.US',mapping_verified=False),first)
            self.assertEqual(client.get.call_count,1)

    def test_failure_is_costed_and_not_retried(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            client=Mock();client.get.side_effect=RuntimeError('fixture failure')
            a=ResumableAcquisition(temp,quota=self.quota(),history_entitled=True,max_units=1,client=client)
            with self.assertRaises(RuntimeError):a.get('eod','FIXTURE.US',mapping_verified=True)
            with self.assertRaisesRegex(RuntimeError,'retry'):a.get('eod','FIXTURE.US',mapping_verified=True)
            with self.assertRaisesRegex(RuntimeError,'exhausted'):a.get('eod','OTHER.US',mapping_verified=True)
            self.assertEqual(client.get.call_count,1)

    def test_stale_quota_and_unverified_entitlements_never_request(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            client=Mock()
            a=ResumableAcquisition(temp,quota={'quota_date_is_current':False},history_entitled=True,max_units=1,client=client)
            with self.assertRaisesRegex(RuntimeError,'Stale'):a.get('eod','FIXTURE.US',mapping_verified=True)
            a.history_entitled=False
            with self.assertRaisesRegex(RuntimeError,'entitlement'):a.get('eod','FIXTURE.US',mapping_verified=True)
            client.get.assert_not_called()
