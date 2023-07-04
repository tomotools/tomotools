from tomotools.utils.tiltseries import TiltSeries


def get_value(path, key):
    with open(path) as file:
        for line in file:
            if line.startswith(f'{key}\t'):
                return line.split()[1].strip()
            elif line.startswith(f'{key} '):
                return line.split()[1].strip()
    return None


def modify_value(path, key, value):
    lines = list()
    with open(path) as file:
        lines = file.readlines()
    for n, line in enumerate(lines):
        if line.startswith(f'{key}\t'):
            lines[n] = f'{key}\t{value}\n'
        elif line.startswith(f'{key} '):
            lines[n] = f'{key} {value}\n'
    with open(path, 'w') as file:
        file.writelines(lines)

    return


def remove_value(path, key):
    lines = list()
    lines_cleaned = list()

    with open(path) as file:
        lines = file.readlines()
    for n, line in enumerate(lines):
        if line.startswith(f'{key}\t'):
            continue
        elif line.startswith(f'{key} '):
            continue
        else:
            lines_cleaned.append(line)

    with open(path, 'w') as file:
        file.writelines(lines_cleaned)

    return


def fake_ctfcom(ts: TiltSeries, binning: int):
    '''
    Create ctfcorrection.com file for your reconstruction folder.

    Does not check whether the required files are there!
    Right now, 300 kV and 2.7 mm Cs are hard-coded.
    '''

    content = ['# Command file to run ctfphaseflip',
               '# Created with tomotools',
               '$setenv IMOD_OUTPUT_FORMAT MRC',
               '$ctfphaseflip -StandardInput',
               f'InputStack  {ts.path.name}',
               f'AngleFile   {ts.mdoc.with_suffix("").stem}.tlt',
               f'OutputFileName	{ts.mdoc.with_suffix("").stem}_ctfcorr.mrc',
               f'TransformFile   {ts.mdoc.with_suffix("").stem}.xf',
               f'DefocusFile    {ts.mdoc.with_suffix("").stem}.defocus',
               'Voltage 300',
               'SphericalAberration 2.7',
               'DefocusTol	50',
               f'PixelSize {ts.angpix()*binning/10}',
               'AmplitudeContrast	0.07',
               'InterpolationWidth	15',
               'ActionIfGPUFails	1,2',
               '$if (-e ./savework) ./savework']

    with open(ts.path.with_name("ctfcorrection.com"), 'w+') as file:
        file.truncate(0)
        file.write('\n'.join(content))

    return


def fix_tiltcom(ts: TiltSeries, thickness: int, fsirt: int, bin: int):
    '''
    Make sure tilt.com file has the right parameters.

    AreTomo irritatingly puts the alignment file as LOCALFILE, remove this.

    '''

    modify_value(ts.path.with_name('tilt.com'),
                 'IMAGEBINNED', str(bin))
    modify_value(ts.path.with_name('tilt.com'),
                 'THICKNESS', str(thickness))
    modify_value(ts.path.with_name('tilt.com'),
                 'InputProjections', f'{ts.path.stem}_ali.mrc')
    modify_value(ts.path.with_name('tilt.com'),
                 'OutputFile', f'{ts.path.parent.name}_full_rec.mrc')

    if get_value(ts.path.with_name("tilt.com"),
                 'FakeSIRTiterations') is not None:
        modify_value(ts.path.with_name('tilt.com'),
                     'FakeSIRTiterations', str(fsirt))

    if get_value(ts.path.with_name("tilt.com"),
                 'LOCALFILE') == ts.path.with_suffix(".xf").name:
        remove_value(ts.path.with_name('tilt.com'), 'LOCALFILE')

    return
