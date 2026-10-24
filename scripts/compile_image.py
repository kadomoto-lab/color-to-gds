"""Convenience frontend: image minimum-size gds-layer + explicit stack."""
import argparse
import sys
from color2gds.__main__ import main

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Legacy-style image / minimum feature / layer inputs. Additional --stack and --out options are passed to color2gds compile.')
    parser.add_argument('image');parser.add_argument('minimum_size_um',type=float);parser.add_argument('layer',type=int)
    known,extra=parser.parse_known_args()
    sys.argv=[sys.argv[0],'compile',known.image,'--min-width-um',str(known.minimum_size_um),
              '--min-space-um',str(known.minimum_size_um),'--gds-layer',str(known.layer),*extra]
    main()
