import importlib.util
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec("torch"), "Optional PyTorch unavailable")
class TMTTests(unittest.TestCase):
    def test_online_learning_and_readonly_observation(self):
        import torch
        from aeon.tmt import ByteRTU
        torch.manual_seed(42)
        model = ByteRTU(dim=8,layers=2)
        optimizer = torch.optim.AdamW(model.parameters(),lr=0.001)
        initial = model.embed.weight.detach().clone()
        loss = model.learn(65,66,optimizer)
        self.assertTrue(torch.isfinite(torch.tensor(loss)))
        self.assertFalse(torch.equal(initial,model.embed.weight))
        parameters = [p.detach().clone() for p in model.parameters()]
        states = model.states.clone()
        summary = model.observe(b"abc")
        self.assertEqual(summary["bytes"],3)
        self.assertFalse(torch.equal(states,model.states))
        self.assertTrue(all(torch.equal(a,b) for a,b in zip(parameters,model.parameters())))

    def test_train_save_reload(self):
        from aeon.tmt import train_file,checkpoint_hint
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp)/"training.txt", Path(tmp)/"small.pt"
            source.write_text("hello world\n")
            result = train_file(source,target,8)
            self.assertEqual(result["steps"],8)
            hint = checkpoint_hint(target,"hello")
            self.assertEqual(hint["bytes"],5)
            self.assertTrue(hint["trained_model"])
            with self.assertRaises(ValueError):
                train_file(source,target,2)
