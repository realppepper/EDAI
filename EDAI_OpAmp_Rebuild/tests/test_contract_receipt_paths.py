import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from opamp_pipeline.validation_03_execution_contract import save_contract_receipt
from opamp_pipeline.validation_01_results import digest


class ContractReceiptPathTests(unittest.TestCase):
    def test_short_name_retains_full_content_hash(self):
        receipt={'status':'passed','evidence':{'source':'test'}}
        with tempfile.TemporaryDirectory() as temp:
            path=save_contract_receipt(temp,'retry_fallback_preflight',receipt)
            self.assertLessEqual(len(path.name),54)
            body=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(body.pop('receipt_sha256'),digest(body))
            self.assertEqual(body,receipt)
            self.assertEqual(save_contract_receipt(temp,'retry_fallback_preflight',receipt),path)

    def test_collision_cannot_overwrite_different_receipt(self):
        with tempfile.TemporaryDirectory() as temp,patch('opamp_pipeline.validation_03_execution_contract.digest',return_value='a'*64):
            path=save_contract_receipt(temp,'test',{'status':'passed'})
            original=path.read_bytes()
            with self.assertRaises(ValueError):save_contract_receipt(temp,'test',{'status':'failed'})
            self.assertEqual(path.read_bytes(),original)

    def test_repeat_tuple_and_path_evidence_after_serialization(self):
        receipt={'status':'passed','evidence':{'range':(0,1),'path':Path('source.cir')}}
        with tempfile.TemporaryDirectory() as temp:
            path=save_contract_receipt(temp,'generated_preflight',receipt)
            original=path.read_bytes()
            self.assertEqual(save_contract_receipt(temp,'generated_preflight',receipt),path)
            normalized=json.loads(original)
            self.assertEqual(normalized['evidence']['range'],[0,1])
            self.assertEqual(normalized['evidence']['path'],'source.cir')
            self.assertEqual(save_contract_receipt(temp,'generated_preflight',normalized),path)
            self.assertEqual(path.read_bytes(),original)


if __name__=='__main__':unittest.main()
