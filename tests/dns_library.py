"""Observable hostname boundary semantics across independent backends."""
import shutil
import unittest
import support as harness
from support import ToolchainCase

class DNSLibrary(ToolchainCase):
    def test_request_validation_agrees_at_DNS_wire_boundaries(self):
        library=(harness.REPO/'lib/dns.nex').read_text()
        library=library.replace('module std::dns;','module dns_validation;',1).replace('test fn ','fn ')
        self.source(library+'\nfn main()->unit !{io}{validation();hostname_boundaries();print(42);}\n'
                    +'test fn boundaries()->unit{validation();hostname_boundaries();}\n')
        self.assertEqual(self.cli('eval')['stdout'],'42\n')
        for profile in ('debug','release'):
            self.assertEqual(self.cli('run','--profile',profile)['stdout'],'42\n')
        self.assertIsNotNone(shutil.which('node'),'Node is required for actual TypeScript agreement')
        self.cli('test','--target','web')

if __name__=='__main__':unittest.main()
