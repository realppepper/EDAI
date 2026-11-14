from copy import deepcopy
import unittest
from opamp_pipeline.support.source_checks import fingerprint
from opamp_pipeline.support.semantic_review import validate_review, attach_review, DIMENSIONS


def fixture():
    packet={'source_pages':{'6':{'text':'VS = 5 V. Common conditions.'}},'rows':[{'id':'ROW-A'}]}
    review={'packet_fingerprint':fingerprint(packet),'reviewer':{'method':'test'},'row_reviews':[{
        'row_id':'ROW-A','checks':{key:{'verdict':'match','explanation':'Source agrees',
        'evidence':[{'pdf_page':6,'quote':'VS = 5 V'}]} for key in DIMENSIONS}}]}
    return packet,review


class SemanticReview(unittest.TestCase):
    def test_evidence_and_input_identity_required(self):
        for change in ('stale','wrong_quote','wrong_page','missing_dimension','unknown_row','duplicate'):
            packet,review=fixture()
            if change=='stale':review['packet_fingerprint']='stale'
            if change=='wrong_quote':review['row_reviews'][0]['checks']['conditions']['evidence'][0]['quote']='VS = 36 V'
            if change=='wrong_page':review['row_reviews'][0]['checks']['conditions']['evidence'][0]['pdf_page']=7
            if change=='missing_dimension':del review['row_reviews'][0]['checks']['footnotes']
            if change=='unknown_row':review['row_reviews'][0]['row_id']='OTHER'
            if change=='duplicate':review['row_reviews'].append(deepcopy(review['row_reviews'][0]))
            with self.subTest(change=change),self.assertRaises(ValueError):validate_review(packet,review)

    def test_changes_are_proposals_and_cannot_overrule_code_conflicts(self):
        packet,review=fixture()
        row=review['row_reviews'][0];row['checks']['inheritance']['verdict']='needs_change'
        with self.assertRaises(ValueError):validate_review(packet,review)
        row['suggested_changes']=[{'field':'conditions','recommendation':'Fix the condition'}]
        report={'summary':{},'rows':[{'candidate_id':'ROW-A','status':'conflict'}]}
        attach_review(report,packet,review)
        self.assertEqual(report['rows'][0]['status'],'conflict')
        self.assertEqual(report['summary']['llm_needs_change_rows'],1)

    def test_absent_and_partial_reviews_stay_pending(self):
        packet,review=fixture();review['row_reviews']=[]
        report={'summary':{},'rows':[{'candidate_id':'ROW-A'}]}
        attach_review(report,packet,review)
        self.assertEqual(report['summary']['llm_pending_rows'],1)
        self.assertEqual(report['semantic_review']['unreviewed_row_ids'],['ROW-A'])
