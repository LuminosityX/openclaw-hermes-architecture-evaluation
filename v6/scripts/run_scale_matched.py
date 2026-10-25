"""Primary Gateway timing/capacity profile with equivalent file and shell capabilities.

The earlier broad OpenClaw / terminal-only Hermes profile is retained as a
configuration contrast, and cannot establish the paired primary advantage.
"""
from runtime import R
import run_scale as S


def main():
    driver = S.DRIVER
    oc = "c['agents']['defaults']['maxConcurrent']=16;p.write_text(json.dumps(c))"
    if driver.count(oc) != 1:
        raise RuntimeError('OpenClaw driver insertion point changed')
    driver = driver.replace(oc, "c['agents']['defaults']['maxConcurrent']=16;c['tools']={'toolSearch':False,'allow':['group:fs','group:runtime'],'exec':{'mode':'full'}};p.write_text(json.dumps(c))")
    h = "c['platform_toolsets']={'api_server':['terminal']};p.write_text(json.dumps(c))"
    if driver.count(h) != 1:
        raise RuntimeError('Hermes driver insertion point changed')
    driver = driver.replace(h, "c['platform_toolsets']={'api_server':['terminal','file']};c['tools']={'tool_search':{'enabled':'off'}};p.write_text(json.dumps(c))")
    compile(driver, 'generated-matched-gateway-driver', 'exec')
    S.DRIVER = driver
    S.RUN_ROOT = R / 'runs-scale-matched-tools'
    S.RESULT_NAME = 'scale-matched-tools.json'
    S.PROFILE = 'matched-file-and-shell-tools'
    S.MEASURE_CAPACITY = False
    S.main()


if __name__ == '__main__':
    main()
