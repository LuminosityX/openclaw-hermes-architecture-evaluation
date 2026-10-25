def read_events(path):
    lines=open(path).read().splitlines();keys=lines[0].split(',')
    return [dict(zip(keys,line.split(','))) for line in lines[1:]]
