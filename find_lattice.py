import os, sys, numpy, pylab
from itertools import product, combinations
from scipy.ndimage import gaussian_filter
from scipy.spatial import Delaunay

def load_image_data(filename, xPix=512, yPix=512, zPix=201):
    """Load the 16-bit raw data from the Visitech Infinity"""
    return numpy.memmap(
        filename, dtype=numpy.uint16, mode='r',
        ).reshape(zPix, xPix, yPix) #FIRST dimension is image number

def get_fft_abs(filename, image_data):
    basename = os.path.splitext(filename)[0]
    fft_abs_name = basename + '_fft_abs.npy'
    fft_data_name = basename + '_fft_data.raw'
    
    if os.path.exists(fft_abs_name) and os.path.exists(fft_data_name):
        print "Loading", os.path.split(fft_abs_name)[1]
        fft_abs = numpy.load(fft_abs_name)
        print "Loading", os.path.split(fft_data_name)[1]
        fft_data = numpy.memmap(fft_data_name, dtype=numpy.complex128, mode='r'
                                ).reshape(image_data.shape)
    else:
        print "Generating fft_abs and fft_data..."
        fft_data = numpy.memmap(fft_data_name, dtype=numpy.complex128,
                                mode='w+', shape=image_data.shape)
        fft_abs = numpy.zeros(image_data.shape[1:])
        for z in range(image_data.shape[0]):
            fft_data[z, :, :] = numpy.fft.fftshift(#Stored shifted!
                numpy.fft.fftn(image_data[z, :, :], axes=(0, 1)))
            fft_abs += numpy.abs(fft_data[z, :, :])
            sys.stdout.write('\rProcessing slice %i'%(z+1))
            sys.stdout.flush()
        numpy.save(fft_abs_name, fft_abs)
        print
    return (fft_data, fft_abs)

def simple_max_finder(a, show_plots=True):
    """Given a 3x3 array with the maximum pixel in the center,
    estimates the x/y position of the true maximum"""

    true_max = []
    interpPoints = numpy.arange(-1, 2)
    for data in (a[:, 1], a[1, :]):
        myFit = numpy.poly1d(numpy.polyfit(
            interpPoints, data, deg = 2))
        true_max.append(-myFit[1]/(2.0*myFit[2]))
    true_max = numpy.array(true_max)

    if show_plots:
        print "Correction:", true_max
        fig = pylab.figure()
        pylab.subplot(1, 3, 1)
        pylab.imshow(a, interpolation='nearest', cmap=pylab.cm.gray)
        pylab.axhline(y=1 + true_max[0])
        pylab.axvline(x=1 + true_max[1])
        pylab.subplot(1, 3, 2)
        pylab.plot(a[:, 1])
        pylab.axvline(x=1 + true_max[0])
        pylab.subplot(1, 3, 3)
        pylab.plot(a[1, :])
        pylab.axvline(x=1 + true_max[1])
        fig.show()

    return true_max

def combinations_with_replacement(iterable, r):
    """
    >>>print([i for i in combinations_with_replacement(['a', 'b', 'c'], 2)])
    [('a', 'a'), ('a', 'b'), ('a', 'c'), ('b', 'b'), ('b', 'c'), ('c', 'c')]
    """
    pool = tuple(iterable)
    n = len(pool)
    for indices in product(range(n), repeat=r):
        if sorted(indices) == list(indices):
            yield tuple(pool[i] for i in indices)

def same_side(point_1, point_2, corner_1, corner_2):
    cp1 = numpy.cross(
        (corner_2[0] - corner_1[0], corner_2[1] - corner_1[1]),
        (point_1[0] - corner_1[0], point_1[1] - corner_1[1]))
    cp2 = numpy.cross(
        (corner_2[0] - corner_1[0], corner_2[1] - corner_1[1]),
        (point_2[0] - corner_1[0], point_2[1] - corner_1[1]))
    if numpy.dot(cp1, cp2) > 0:
        return True
    return False

def in_triangle(point, corners):
    a, b, c = corners
    if same_side(point, a, b, c):
        if same_side(point, b, a, c):
            if same_side(point, c, a, b):
                return True
    return False

def find_bounding_triangle(point, possible_corners):
    for corners in combinations(possible_corners, 3):
        if in_triangle(point, corners):
            return corners
    raise UserWarning("Point not contained in corners")

def three_point_weighted_average(position, corners, values):
    """Given three 2D positions, and three values, computes a weighted
    average of the values for some interior position. Equivalent to
    interpolating with a plane."""
    x, y = position
##    print
##    print "x, y:", x, y
    ((x1, y1), (x2, y2), (x3, y3)) = corners
##    print "Corners:"
##    print x1, y1
##    print x2, y2
##    print x3, y3
    (z1, z2, z3) = values
##    print "Values:", z1.shape, z2.shape, z3.shape
    denom = y1*(x3 - x2) + y2*(x1 - x3) + y3*(x2 - x1)
    w1 = (y3 - y2)*x + (x2 - x3)*y + x3*y2 - x2*y3
    w2 = (y1 - y3)*x + (x3 - x1)*y + x1*y3 - x3*y1
    w3 = (y2 - y1)*x + (x1 - x2)*y + x2*y1 - x1*y2
##    print "Weights:"
##    print w1 * 1.0 / denom
##    print w2 * 1.0 / denom
##    print w3 * 1.0 / denom
##    raw_input()
    return (w1*z1 + w2*z2 + w3*z3) * -1.0 / denom

def spike_filter(fft_abs):
    f = gaussian_filter(numpy.log(1 + fft_abs), sigma=0.5)
    f = f - gaussian_filter(f, sigma=(0, 4))
    f = f - gaussian_filter(f, sigma=(4, 0))
    f = abs(f)
    f -= f.mean()
    f *= 1.0 / f.std()
    return f

def find_spikes(fft_abs, filtered_fft_abs, extent=15, num_spikes=150,
                display=True, animate=False):
    """Finds spikes in the sum of the 2D ffts of an image stack"""
    center_pix = numpy.array(fft_abs.shape)//2
    log_fft_abs = numpy.log(1 + fft_abs)
    filtered_fft_abs = numpy.array(filtered_fft_abs)

    if display:
        image_extent=[-0.5 - center_pix[1],
                     filtered_fft_abs.shape[1] - 0.5 - center_pix[1],
                     filtered_fft_abs.shape[0] - 0.5 - center_pix[0],
                     -0.5 - center_pix[0]]
        fig = pylab.figure()
        pylab.subplot(1, 2, 1)
        pylab.imshow(log_fft_abs, cmap=pylab.cm.gray,
                     interpolation='nearest', extent=image_extent)
        pylab.title('Average Fourier magnitude')
        pylab.subplot(1, 2, 2)
        pylab.imshow(numpy.array(filtered_fft_abs), cmap=pylab.cm.gray,
                     interpolation='nearest', extent=image_extent)
        pylab.title('Filtered average Fourier magnitude')
        fig.show()

    coords = []
    if animate:
        fig = pylab.figure()
        print 'Center pixel:', center_pix
    for i in range(num_spikes):
        coords.append(
            numpy.array(numpy.unravel_index(
                filtered_fft_abs.argmax(), filtered_fft_abs.shape)))
        c = coords[-1]
        xSl = slice(max(c[0]-extent, 0),
                    min(c[0]+extent, filtered_fft_abs.shape[0]))
        ySl = slice(max(c[1]-extent, 0),
                    min(c[1]+extent, filtered_fft_abs.shape[1]))
        filtered_fft_abs[xSl, ySl] = 0
        if animate:
            print i, ':', c
            pylab.clf()
            pylab.subplot(1, 2, 1)
            pylab.imshow(
                filtered_fft_abs, cmap=pylab.cm.gray, interpolation='nearest')
            pylab.colorbar()
            pylab.subplot(1, 2, 2)
            pylab.plot(filtered_fft_abs.max(axis=1))
            fig.show()
            fig.canvas.draw()
            if i == 0:
                raw_input('.')

    coords = [c - center_pix for c in coords]
    coords = sorted(coords, key=lambda x: x[0]**2 + x[1]**2)

    return coords #Lattice k-vectors, sorted by vector magnitude

def test_basis(coords, basis_vectors, tolerance, verbose=False):
    #Checks for expected lattice, returns the points found and halts on failure.
    points_found = list(basis_vectors)
    num_vectors = 2
    searching = True
    while searching:
        if verbose: print "Looking for combinations of %i basis vectors."%(
            num_vectors)
        lattice = [sum(c) for c in
                 combinations_with_replacement(basis_vectors, num_vectors)]
        if verbose: print "Expected lattice points:", lattice
        for i, lat in enumerate(lattice):
            for c in coords:
                dif = numpy.sqrt(((lat - c)**2).sum())
                if dif < tolerance:
                    if verbose:
                        print "Found lattice point:", c
                        print " Distance:", dif
                        if len(basis_vectors) == 1:
                            print " Fundamental:", c * 1.0 / num_vectors
                    points_found.append(c)
                    break
            else: #Fell through the loop
                if verbose: print "Expected lattice point not found"
                searching = False
        if not searching: return (num_vectors, points_found)
        num_vectors += 1

def get_precise_basis(coords, basis_vectors, fft_abs, tolerance, verbose=False):
    #Uses the expected lattice to estimate precise values of the basis.
    if verbose: print "\nAdjusting basis vectors to match lattice..."
    center_pix = numpy.array(fft_abs.shape) // 2
    basis_vectors = list(basis_vectors)
    spike_indices = []
    spike_locations = []
    num_vectors = 2
    searching = True
    while searching:
        combinations = [
            c for c in combinations_with_replacement(basis_vectors, num_vectors)
            ]
        combination_indices = [
            c for c in combinations_with_replacement((0, 1, 2), num_vectors)]
        for i, comb in enumerate(combinations):
            lat = sum(comb)
            key = tuple([combination_indices[i].count(v) for v in (0, 1, 2)])
            for c in coords:
                dif = numpy.sqrt(((lat - c)**2).sum())
                if dif < tolerance:
                    p = c + center_pix
                    true_max = c + simple_max_finder(
                        fft_abs[p[0] - 1:p[0] + 2,
                                p[1] - 1:p[1] + 2], show_plots=False)
                    if verbose:
                        print "Found lattice point:", c
                        print "Estimated position:", true_max
                        print "Lattic index:", key
                    spike_indices.append(key)
                    spike_locations.append(true_max)
                    break
            else: #Fell through the loop
                if verbose: print "Expected lattice point not found"
                searching = False
        if not searching: #Given the spikes found, estimate the basis
            A = numpy.array(spike_indices)
            v = numpy.array(spike_locations)
            precise_basis_vectors, residues, rank, s = numpy.linalg.lstsq(A, v)
            if verbose:
                print "Precise basis vectors:"
                print precise_basis_vectors
                print "Residues:", residues
                print "Rank:", rank
                print "s:", s
                print
            return precise_basis_vectors            
        num_vectors += 1

def get_basis_vectors(fft_abs, coords, extent=15, tolerance=3., verbose=False):
    for i in range(len(coords)): #Where to start looking.
        basis_vectors = []
        precise_basis_vectors = []
        for c, coord in enumerate(coords):
            if c < i:
                continue

            if c == 0:
                if max(abs(coord)) > 0:
                    print "c:", c
                    print "Coord:", coord
                    print "Coordinates:"
                    for x in coords: print x
                    raise UserWarning('No peak at the central pixel')
                else:
                    continue #Don't look for harmonics of the DC term

            if coord[0] < 0 or (coord[0] == 0 and coord[1] < 0):
                #Ignore the negative versions
                if verbose: print "\nIgnoring:", coord
            else:
                #Check for harmonics
                if verbose: print "\nTesting:", coord
                num_vectors, points_found = test_basis(
                    coords, [coord], tolerance=tolerance, verbose=verbose)
                if num_vectors > 3:
                    #We found enough harmonics. Keep it, for now.
                    basis_vectors.append(coord)
                    center_pix = numpy.array(fft_abs.shape)//2
                    furthest_spike = points_found[-1] + center_pix
                    if verbose:
                        print "Appending", coord
                        print "%i harmonics found, at:"%(num_vectors-1)
                        for p in points_found:
                            print ' ', p

                    if len(basis_vectors) > 1:
                        if verbose:
                            print "\nTesting combinations:", basis_vectors
                        num_vectors, points_found = test_basis(
                            coords, basis_vectors, tolerance=tolerance,
                            verbose=verbose)
                        if num_vectors > 3:
                            #The combination predicts the lattice
                            if len(basis_vectors) == 3:
                                #We're done; we have three consistent vectors.
                                precise_basis_vectors = get_precise_basis(
                                    coords, basis_vectors, fft_abs,
                                    tolerance=tolerance, verbose=verbose)
                                (x_1, x_2, x_3) = sorted(
                                    precise_basis_vectors,
                                    key=lambda x: abs(x[0]))
                                possibilities = sorted(
                                    ([x_1, x_2, x_3],
                                     [x_1, x_2, -x_3],
                                     [x_1, -x_2, x_3],
                                     [x_1, -x_2, -x_3]),
                                    key=lambda x:(numpy.array(sum(x))**2).sum())
                                if verbose:
                                    print "Possible triangle combinations:"
                                    for p in possibilities: print " ", p
                                precise_basis_vectors = possibilities[0]
                                return precise_basis_vectors
                        else:
                            #Blame the new guy, for now.
                            basis_vectors.pop()
    else:
        raise UserWarning(
            "Basis vector search failed. Diagnose by running with verbose=True")

def get_shift_vector(
    fourier_lattice_vectors, fft_data, filtered_fft_abs,
    num_harmonics=3, outlier_phase=1.,
    verbose=True, display=True):
    if verbose: print "\nCalculating shift vector..."
    center_pix = numpy.array(filtered_fft_abs.shape) // 2
    harmonic_pixels = []
    values = {}
    for v in fourier_lattice_vectors:
        harmonic_pixels.append([])
        for i in range(1, num_harmonics+1):
            expected_pix = (numpy.round((i * v)) + center_pix).astype(int)
            roi = filtered_fft_abs[expected_pix[0] - 1:expected_pix[0] + 2,
                                   expected_pix[1] - 1:expected_pix[1] + 2]
            shift = -1 + numpy.array(
                numpy.unravel_index(roi.argmax(), roi.shape))
            actual_pix = expected_pix + shift - center_pix 
            if verbose:
                print "Expected pixel:", expected_pix - center_pix
                print "Shift:", shift
                print "Brightest neighboring pixel:", actual_pix
            harmonic_pixels[-1].append(tuple(actual_pix))
            values[harmonic_pixels[-1][-1]] = []
    for z in range(fft_data.shape[0]):
        for hp in harmonic_pixels:
            for p in hp:
                values[p].append(
                    fft_data[z, p[0] + center_pix[0], p[1] + center_pix[1]])
    slopes = []
    K = []
    if display: fig = pylab.figure()
    for hp in harmonic_pixels:
        for n, p in enumerate(hp):
            values[p] = numpy.unwrap(numpy.angle(values[p]))
            slope = numpy.polyfit(range(len(values[p])), values[p], deg=1)[0]
            values[p] -= slope * numpy.arange(len(values[p]))
            values[p] -= values[p].mean()
            if abs(values[p]).mean() < outlier_phase:
                K.append(p * (-2. * numpy.pi / numpy.array(fft_data.shape[1:])))
                slopes.append(slope)
            else:
                if verbose: print "Ignoring outlier:", p
            if display: pylab.plot(values[p],'.-', label=repr(p))
    if display:
        pylab.title('This should look like noise. Sudden jumps mean bad data!')
        pylab.ylabel('Deviation from expected phase')
        pylab.xlabel('Image number')
        pylab.grid()
        pylab.legend(prop={'size':8})
        pylab.axis('tight')
        x_limits = 1.05 * numpy.array(pylab.xlim())
        x_limits -= x_limits[-1] * 0.025
        pylab.xlim(x_limits)
        fig.show()

    x_s, residues, rank, s = numpy.linalg.lstsq(
        numpy.array(K), numpy.array(slopes))
    if verbose:
        print "Shift vector:", x_s
        print "Residues:", residues
        print "Rank:", rank
        print "s:", s
    return x_s

def generate_lattice(
    image_shape, lattice_vectors, center_pix='image', edge_buffer=2):

    if center_pix == 'image':
        center_pix = numpy.array(image_shape) // 2
    else: ##Express the center pixel in terms of the lattice vectors
        center_pix = numpy.array(center_pix) - (numpy.array(image_shape) // 2)
        lattice_components = numpy.linalg.solve(
            numpy.vstack(lattice_vectors[:2]).T,
            center_pix)
        lattice_components -= lattice_components // 1
        center_pix = (lattice_vectors[0] * lattice_components[0] +
                      lattice_vectors[1] * lattice_components[1] +
                      numpy.array(image_shape)//2)

    num_vectors = int(#Probably an overestimate
        max(image_shape) / numpy.sqrt(lattice_vectors[0]**2).sum())
    lower_bounds = (edge_buffer, edge_buffer)
    upper_bounds = (image_shape[0] - edge_buffer, image_shape[1] - edge_buffer)
    i, j = numpy.mgrid[-num_vectors:num_vectors, -num_vectors:num_vectors]
    i = i.reshape(i.size, 1)
    j = j.reshape(i.size, 1)
    lp = i*lattice_vectors[0] + j*lattice_vectors[1] + center_pix
    valid = numpy.all(lower_bounds < lp, 1) * numpy.all(lp < upper_bounds, 1)
    lattice_points = list(lp[valid])
    return lattice_points

def get_offset_vector(
    which_image, direct_lattice_vectors,
    verbose=True, display=True, show_interpolation=True):
    if verbose: print "\nCalculating offset vector..."
    ws = 2 + 2*int(max(
        [abs(v).max() for v in direct_lattice_vectors])) #Window size
    if verbose: print "Window size:", ws
    window = numpy.zeros([ws]*2).astype(numpy.int64)
    lattice_points = generate_lattice(
        which_image.shape, direct_lattice_vectors, edge_buffer=2+ws)
    for lp in lattice_points:
        x, y = numpy.round(lp).astype(int)
        window += which_image[x:x+ws, y:y+ws]
    if display:
        fig = pylab.figure()
        pylab.imshow(window, interpolation='nearest', cmap=pylab.cm.gray)
        pylab.title('Lattice average\nThis should look like round blobs')
        fig.show()
    buffered_window = numpy.array(window)
    buffered_window[:2, :] = 0
    buffered_window[-2:, :] = 0
    buffered_window[:, :2] = 0
    buffered_window[:, -2:] = 0
    while True: #Don't want maxima on the edges
        max_pix = numpy.unravel_index(buffered_window.argmax(), window.shape)
        if ((3 < max_pix[0] < window.shape[0] - 3) and
            (3 < max_pix[1] < window.shape[1] - 3)):
            break
        else:
            buffered_window = gaussian_filter(buffered_window, sigma=2)
    if verbose: print "Maximum pixel in lattice average:", max_pix
    correction = simple_max_finder(
        window[max_pix[0]-1:max_pix[0]+2, max_pix[1]-1:max_pix[1]+2],
        show_plots=show_interpolation)
    offset_vector = max_pix + correction + numpy.array(which_image.shape)//2
    if verbose: print "Offset vector:", offset_vector
    return offset_vector

def show_lattice_overlay(
    image_data, direct_lattice_vectors, offset_vector, shift_vector):
    fig = pylab.figure()
    s = 0
    while True:
        pylab.clf()
        showMe = image_data[s, :, :]
        dots = numpy.zeros(list(showMe.shape) + [4])
        lattice_points = generate_lattice(
            showMe.shape, direct_lattice_vectors,
            center_pix=offset_vector + shift_vector * s)
        for lp in lattice_points:
            x, y = numpy.round(lp).astype(int)
            dots[x, y, 0::3] = 1
        pylab.imshow(showMe, cmap=pylab.cm.gray, interpolation='nearest')
        pylab.imshow(dots, interpolation='nearest')
        pylab.title("Red dots show the calculated illumination pattern")
        fig.show()
        fig.canvas.draw()
        new_s = raw_input("Next frame [exit]:")
        if new_s == '':
            print "Exiting"
            break
        try:
            s = int(new_s)
        except ValueError:
            print "Response not understood. Exiting display."
            break
        s %= image_data.shape[0]
        print "Displaying frame %i"%(s)
    return None

def combine_lattices(
    direct_lattice_vectors, shift_vector, offset_vector='image',
    xPix=120, yPix=120, step_size=1, num_steps=200, edge_buffer=2,
    verbose=True):
    if verbose: print "Combining lattices..."
    if offset_vector == 'image':
        offset_vector = numpy.array((xPix//2, yPix//2))
    spots = []
    for i in range(num_steps):
        spots.append([])
        if verbose:
            sys.stdout.write('\rz: %04i'%(i+1))
            sys.stdout.flush()
        spots[-1] += generate_lattice(
            image_shape=(xPix, yPix),
            lattice_vectors=direct_lattice_vectors,
            center_pix=offset_vector + i * step_size * shift_vector,
            edge_buffer=edge_buffer)
    if verbose: print
    return spots

def show_illuminated_points(
    direct_lattice_vectors, shift_vector, offset_vector='image',
    xPix=120, yPix=120, step_size=1, num_steps=200, verbose=True):
    spots = sum(combine_lattices(
        direct_lattice_vectors, shift_vector, offset_vector,
        xPix, yPix, step_size, num_steps, verbose), [])
    fig=pylab.figure()
    pylab.plot([p[1] for p in spots], [p[0] for p in spots], '.')
    pylab.xticks(range(yPix))
    pylab.yticks(range(xPix))
    pylab.grid()
    pylab.axis('equal')
    fig.show()
    fig.canvas.draw()
    return fig

def get_lattice_vectors(
    filename='QDots.raw',
    xPix=512,
    yPix=512,
    zPix=201,
    extent=15,
    num_spikes=150,
    tolerance=3.,
    num_harmonics=3,
    outlier_phase=1.,
    verbose=False,
    display=False,
    animate=False,
    show_interpolation=False,
    show_lattice=False):
    """Given the 2D ffts of an swept-field confocal image stack, finds
    the basis vectors of the illumination lattice pattern."""

    image_data = load_image_data(filename, xPix=xPix, yPix=yPix, zPix=zPix)
    fft_data, fft_abs = get_fft_abs(filename, image_data) #DC term at center
    filtered_fft_abs = spike_filter(fft_abs)

    """Find candidate spikes in the Fourier domain"""
    coords = find_spikes(
        fft_abs, filtered_fft_abs, extent=extent, num_spikes=num_spikes,
        display=display, animate=animate)
    """Use these candidate spikes to determine the Fourier-space lattice"""
    if verbose: print "Finding Fourier-space lattice vectors..."
    basis_vectors = get_basis_vectors(
        fft_abs, coords, extent=extent, tolerance=tolerance, verbose=verbose)
    if verbose:
        print "Fourier-space lattice vectors:"
        for v in basis_vectors:
            print v, "(Magnitude", numpy.sqrt((v**2).sum()), ")"
    """Correct the Fourier-space vectors by constraining their sum to be zero"""
    error_vector = sum(basis_vectors)
    corrected_basis_vectors = [
        v - ((1./3.) * error_vector) for v in basis_vectors]
    if verbose:
        print "Fourier-space lattice vector triangle sum:", error_vector
        print "Corrected Fourier-space lattice vectors:"
        for v in corrected_basis_vectors:
            print v            
    """Determine the real-space lattice from the Fourier-space lattice"""
    area = numpy.cross(corrected_basis_vectors[0], corrected_basis_vectors[1])
    rotate_90 = ((0., -1.), (1., 0.))
    direct_lattice_vectors = [
        numpy.dot(v, rotate_90) * fft_abs.shape / area
        for v in corrected_basis_vectors]
    if verbose:
        print "Real-space lattice vectors:"
        for v in direct_lattice_vectors:
            print v, "(Magnitude", numpy.sqrt((v**2).sum()), ")"
        print "Lattice vector triangle sum:", sum(direct_lattice_vectors)
        print "Unit cell area: (%0.2f)^2 square pixels"%(numpy.sqrt(
            numpy.cross(direct_lattice_vectors[0], direct_lattice_vectors[1])))
    """Use the Fourier lattice and the image data to measure shift and offset"""
    shift_vector = get_shift_vector(
        corrected_basis_vectors, fft_data, filtered_fft_abs,
        num_harmonics=num_harmonics, outlier_phase=outlier_phase,
        verbose=verbose, display=display)

    offset_vector = get_offset_vector(
        which_image=image_data[0, :, :],
        direct_lattice_vectors=direct_lattice_vectors,
        verbose=verbose, display=display, show_interpolation=show_interpolation)
    """Use the offset vector to correct the shift vector"""
    final_offset_vector = get_offset_vector(
        which_image=image_data[-1, :, :],
        direct_lattice_vectors = direct_lattice_vectors,
        verbose=False, display=False, show_interpolation=False)
    final_lattice = generate_lattice(
        image_data.shape[1:], direct_lattice_vectors,
        center_pix=offset_vector + (image_data.shape[0] - 1) * shift_vector)
    closest_approach = 1e12
    for p in final_lattice:
        dif = p - final_offset_vector
        distance_sq = (dif**2).sum()
        if distance_sq < closest_approach:
            closest_lattice_point = p
            closest_approach = distance_sq
    shift_error = closest_lattice_point - final_offset_vector
    movements = image_data.shape[0] - 1
    corrected_shift_vector = shift_vector - (shift_error * 1.0 / movements)
    if verbose:
        print "\nCorrecting shift vector..."
        print " Initial shift vector:", shift_vector
        print " Final offset vector:", final_offset_vector
        print " Closest predicted lattice point:", closest_lattice_point
        print " Error:", shift_error, "in", movements, "movements"
        print " Corrected shift vector:", corrected_shift_vector, '\n'

    if show_lattice:
        show_lattice_overlay(
            image_data, direct_lattice_vectors,
            offset_vector, corrected_shift_vector)

    return (corrected_basis_vectors, direct_lattice_vectors,
            corrected_shift_vector, offset_vector)

def find_interpolation_neighbors(
    new_grid_x, new_grid_y,
    direct_lattice_vectors, shift_vector, offset_vector,
    num_steps=186, display=False):
    """We want to convert our scattered scan grid to the Cartesian
    grid that Enderlein's trick expects. For each point on the desired
    grid, this function finds three neighboring scattered scan points
    suitable for interpolating the value at the desired point."""
    """Represent the new grid in terms of lattice coordinates"""
    new_grid = numpy.array(numpy.meshgrid(#Arguments backwards from expected!
        new_grid_y, new_grid_x))[::-1, :, :].reshape(
            2, new_grid_x.size*new_grid_y.size)
    V = numpy.vstack(direct_lattice_vectors[:2]).T
    new_grid_lattice_coordinates = numpy.linalg.solve(#Lattice coordinates
        V, new_grid - offset_vector.reshape(2, 1)) #Relative to central spot
    #Return to pixel coordinates, but now modulo the unit cell
    new_grid_in_unit_cell = numpy.dot(
        V, numpy.mod(new_grid_lattice_coordinates, 1))
    if display:
        print "Plotting new grid..."
        fig = pylab.figure()
        for i in range(2):
            pylab.subplot(1, 2, i+1)
            pylab.imshow(
                new_grid_in_unit_cell.reshape(
                    2, new_grid_x.size, new_grid_y.size)[i, :, :],
                interpolation='nearest')
        fig.show()
    """Represent the illumination grid in terms of lattice coordinates"""
    scan_positions = shift_vector * numpy.arange(num_steps
                                                 ).reshape(num_steps, 1)
    scan_positions_lattice_coordinates = numpy.linalg.solve(V, scan_positions.T)
    scan_positions_in_unit_cell = numpy.dot(
        V, numpy.mod(scan_positions_lattice_coordinates, 1))
    scan_positions_in_padded_cell = [scan_positions_in_unit_cell +
                                     i*direct_lattice_vectors[0].reshape(2, 1) +
                                     j*direct_lattice_vectors[1].reshape(2, 1)
                                     for i in (0, -1, 1)
                                     for j in (0, -1, 1)]
    """Triangulate the illumination grid"""
    print "Triangulating..."
    triangles = Delaunay(numpy.concatenate(
        scan_positions_in_padded_cell, axis=1).T)
    print "Done."
    if display:
        print "Plotting triangles..."
        fig = pylab.figure()
        for p in scan_positions_in_padded_cell:
            pylab.plot(p[1, :], p[0, :], '.')
        pylab.axis('equal')
        fig.show()
        fig = pylab.figure()
        for t in triangles.points[triangles.vertices]:
            pylab.plot(list(t[:, 1]) + [t[0, 1]],
                       list(t[:, 0]) + [t[0, 0]], 'r-')
        pylab.axis('equal')
        fig.show()
    """Search the illumination grid for the new grid points"""
    print "Finding bounding triangles..."
    simplices = triangles.find_simplex(new_grid_in_unit_cell.T)
    print "Done."
    if display:
        print "Plotting a few spots in their triangles..."
        fig = pylab.figure()
        for i in range(100):
            p = new_grid_in_unit_cell[:, i]
            t = triangles.points[triangles.vertices[simplices[i]]]
            pylab.plot(p[1], p[0], 'b.')
            pylab.plot(list(t[:, 1]) + [t[0, 1]],
                       list(t[:, 0]) + [t[0, 0]], 'r-')
        pylab.axis('equal')
        fig.show()
    """For each new grid point, in which three frames is it illuminated?"""
    neighboring_vertices = triangles.vertices[simplices]
    frames_with_neighboring_illumination = numpy.mod(neighboring_vertices,
                                                     num_steps)
    neighbor_relative_positions = triangles.points[
        neighboring_vertices] - new_grid_in_unit_cell.T.reshape(
            new_grid_in_unit_cell.shape[1], 1, 2)
    neighbor_absolute_positions = (
        neighbor_relative_positions +
        new_grid.T.reshape(new_grid.shape[1], 1, 2))
    xs, ys = new_grid_x.size, new_grid_y.size
    return (new_grid.reshape(2, xs, ys),
            frames_with_neighboring_illumination.T.reshape(3, xs, ys),
            neighbor_absolute_positions.T.reshape(2, 3, xs, ys))

def display_neighboring_frames(
    data_source, xPix, yPix, zPix,
    new_grid, frames_with_neighboring_illumination, neighbor_absolute_positions
    ):
    print "Displaying neighboring frames..."
    """Display the neighboring frames"""
    image_data = load_image_data(data_source, xPix, yPix, zPix)
    from random import randint
    fig = pylab.figure()
    while True:
        i = randint(0, new_grid.shape[1] - 1)
        j = randint(0, new_grid.shape[2] - 1)
        p = new_grid[:, i, j]
        n = frames_with_neighboring_illumination[:, i, j]
        n_pos = neighbor_absolute_positions[:, :, i, j]
        print "Grid point", p, "has neighbors in frames", n
        print "with positions:"
        for n_p in n_pos:
            print n_p
        pylab.clf()
        pylab.suptitle("Illumination near grid point at %0.2f, %0.2f"%(
            p[0], p[1]))
        x, y = numpy.round(p)
        print "x, y:", x, y
        footprint = 20
        for i, f in enumerate(n):
            pylab.subplot(2, 2, i+1)
            showMe = numpy.array(image_data[f,
                                            max(x-footprint, 0):x+footprint+1,
                                            max(y-footprint, 0):y+footprint+1])
            pylab.imshow(showMe, cmap=pylab.cm.gray, interpolation='nearest')
            if showMe.shape == (2*footprint+1, 2*footprint+1):
                central_dot = numpy.zeros(showMe.shape + (4,))
                central_dot[footprint, footprint, 0::3] = 1
                pylab.imshow(central_dot, interpolation='nearest')
            pylab.title("Frame %i"%(f))
        pylab.subplot(2, 2, 4)
        pylab.plot(list(n_pos[1, :]) + [n_pos[1, 0]],
                   list(n_pos[0, :]) + [n_pos[0, 0]], 'b.-')
        pylab.plot(p[1], p[0], 'rx', markersize=20)
        pylab.axis('equal')
        pylab.grid()
        ax = pylab.gca()
        ax.set_ylim(ax.get_ylim()[::-1])
        fig.show()
        fig.canvas.draw()
        raw_input()
    return None
