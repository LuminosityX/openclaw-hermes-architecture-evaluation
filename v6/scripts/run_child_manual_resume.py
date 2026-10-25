"""Fresh paired handoff faults plus actual documented native client recovery.
Earlier automatic-only cases remain untouched and are reported separately.
"""
import os
from runtime import R, OLD, save
from run_child_recovery import run_case


def main():
    os.chdir(OLD)
    results=[]
    for unit in range(1,4):
        for family in (['openclaw','hermes'] if unit%2 else ['hermes','openclaw']):
            results.append(run_case(unit,family,True,manual_followup=True))
            save(R/'results/child-standard-resume.json',results)
    print('CHILD_STANDARD_CLIENT_RESUME_COMPLETE',len(results),flush=True)


if __name__=='__main__':main()
