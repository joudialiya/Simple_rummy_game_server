import unittest
from main import is_run, is_set, decode_card

class MainTest(unittest.TestCase):
  def test_is_set(self):
    for i in range(0, 14):
      meld = [chr(0x1F0A1 + i), chr(0x1F0B1 + i), chr(0x1F0C1 + i), chr(0x1F0D1 + i)]
      self.assertTrue(is_set(meld))
  def test_is_run(self):
    melds = [
      ["🂡", "🂢", "🂣"],
      ["🂤", "🂥", "🂦"],
      ["🂪", "🂫", "🂭"],
    ]
    for meld in melds:
      self.assertTrue(is_run(meld))
    
    melds = [
      ["🂪", "🂫", "🂽"]
    ]
    
    for meld in melds:
      self.assertFalse(is_run(meld), [decode_card(card) for card in meld])