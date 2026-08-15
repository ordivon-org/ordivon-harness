import unittest

from scripts.assess_tool_surface_ablation import assess


class TS11ToolSurfaceAblationTests(unittest.TestCase):
    def test_real_provider_schema_is_smaller_and_selected_tools_are_identical(self):
        value=assess()
        self.assertEqual(value['broad']['toolNames'],['read_workspace','patch_workspace','run_check','diff_workspace'])
        self.assertEqual(value['lazy']['toolNames'],['read_workspace','run_check'])
        self.assertGreater(value['delta']['providerSchemaBytesRemoved'],0)
        self.assertGreater(value['delta']['providerSchemaReductionRatio'],0)
        self.assertTrue(value['invariants']['selectedDefinitionDigestsUnchanged'])
        self.assertFalse(value['invariants']['authorityExpanded'])
    def test_behavior_claim_remains_unproven(self):
        value=assess()
        self.assertFalse(value['invariants']['providerBehaviorCompared'])
        self.assertIn('does not claim higher model accuracy',value['behaviorBoundary'])

if __name__ == '__main__':
    unittest.main()
