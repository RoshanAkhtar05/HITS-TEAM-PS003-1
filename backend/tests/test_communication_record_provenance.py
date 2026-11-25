import unittest
from pathlib import Path

from preprocessor.Chats_Social.email_preprocessor import preprocess_email
from preprocessor.Chats_Social.chat_preprocessor import preprocess_chat
from preprocessor.Chats_Social.social_preprocessor import preprocess_social

DATA = Path(__file__).resolve().parents[1] / "Graph_Integration_Layer" / "data"


class CommunicationRecordProvenanceTests(unittest.TestCase):
    def test_multiple_email_messages_are_all_processed_with_ordinals(self):
        result = preprocess_email(str(DATA / "emails.txt"))
        self.assertGreaterEqual(len(result["relations"]), 3)
        ordinals = {r.get("source_record_number") for r in result["relations"]}
        self.assertEqual(ordinals, {1, 2, 3})
        self.assertTrue(all("emails.txt:email-message-" in r.get("provenance", "") for r in result["relations"]))

    def test_chat_relations_keep_one_based_message_ordinals(self):
        result = preprocess_chat(str(DATA / "chat.txt"))
        messages = [r for r in result["relations"] if r.get("relation") == "MESSAGED"]
        self.assertEqual(len(messages), 17)
        self.assertEqual(messages[0].get("source_record_number"), 1)
        self.assertEqual(messages[-1].get("source_record_number"), 17)

    def test_social_relations_keep_source_post_ordinals(self):
        result = preprocess_social(str(DATA / "social.json"))
        posted = [r for r in result["relations"] if r.get("relation") == "POSTED_ON"]
        self.assertTrue(posted)
        self.assertTrue(all(isinstance(r.get("source_record_number"), int) and r["source_record_number"] >= 1 for r in posted))


if __name__ == "__main__":
    unittest.main()
