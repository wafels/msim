import sys, os, pprint, numpy, pylab
import array_illumination
from scipy.ndimage import gaussian_filter, interpolation
from scipy.signal import gaussian

pylab.close('all')

"""Default values, might be overwritten below:"""
num_harmonics = 3
scan_type = 'visitech'
scan_dimensions = None

"""Menagerie of data sources. Uncomment one of these lines:"""
data_filename, lake_filename, xPix, yPix, zPix, steps, extent, scan_type, scan_dimensions = (
    '07_4_pix_spots_1_pix_shifts_tubules.raw',
    '02_4_pix_spots_1_pix_steps.raw',
    1064, 1120, 340, 340, 20, 'dmd', (20, 17))


background_filename, background_zPix = 'background.raw', 340

data_dir = '2011_09_27'

##Don't edit below here
data_filename = os.path.join(os.getcwd(), data_dir, data_filename)
lake_filename = os.path.join(os.getcwd(), data_dir, lake_filename)
background_filename = os.path.join(os.getcwd(), data_dir, background_filename)
print "Data source:", data_filename
print "Calibration source:", lake_filename
print "Background source:", background_filename

"""Find a set of shift vectors which characterize the illumination"""
print "\nDetecting illumination lattice parameters..."
(lattice_vectors, shift_vector, offset_vector,
 intensities_vs_galvo_position, background_frame
 ) = array_illumination.get_lattice_vectors(
     filename=data_filename, lake=lake_filename, bg=background_filename,
     use_lake_lattice=True,
     xPix=xPix, yPix=yPix, zPix=zPix, bg_zPix=background_zPix,
     extent=extent, #Important to get this right. '20' for 1024/1344
     num_spikes=300,
     tolerance=3.5,
     num_harmonics=num_harmonics,
     outlier_phase=1.,
     calibration_window_size=10,
     scan_type=scan_type,
     scan_dimensions=scan_dimensions,
     verbose=True, #Useful for debugging
     display=True, #Useful for debugging
     animate=False, #Useful to see if 'extent' is right
     show_interpolation=False, #Fairly low-level debugging
     show_calibration_steps=False, #Useful for debugging
     show_lattice=True) #Very useful for checking validity
print "Lattice vectors:"
for v in lattice_vectors:
    print v
print "Shift vector:"
pprint.pprint(shift_vector)
print "Initial position:"
print offset_vector

##"""Show a representative region of the illumination scan pattern"""
##spots = array_illumination.show_illuminated_points(
##    lattice_vectors, shift_vector, offset_vector='image',
##    xPix=500, yPix=500, step_size=1, num_steps=steps)

"""Define a new Cartesian grid for Enderlein's trick:"""
new_grid_x = numpy.linspace(0, xPix-1, xPix)
new_grid_y = numpy.linspace(0, yPix-1, yPix)

"""Interpolate the neighboring illumination points to calculate a
higher resolution image"""
window_footprint = 10 #For now, make this an even number
aperture_size = 4
smoothing_sigma = 0
show_steps = False
show_slices = False
verbose = True
intermediate_data = True

basename = os.path.splitext(data_filename)[0]
enderlein_image_name = basename + '_enderlein_image.raw'

if os.path.exists(enderlein_image_name):
    print "\nEnderlein image already calculated."
    print "Loading", os.path.split(enderlein_image_name)[1]
    enderlein_image = numpy.fromfile(
        enderlein_image_name, dtype=float
        ).reshape(new_grid_x.shape[0], new_grid_y.shape[0])
else:
    print "\nCalculating Enderlein image"
    print
    if show_steps or show_slices: fig = pylab.figure()
    enderlein_image = numpy.zeros(
        (new_grid_x.shape[0], new_grid_y.shape[0]), dtype=numpy.float)
    enderlein_normalization = numpy.zeros_like(enderlein_image)
    this_frames_image = numpy.zeros_like(enderlein_image)
    this_frames_normalization = numpy.zeros_like(enderlein_image)
    if intermediate_data:
        cumulative_sum = numpy.memmap(
            basename + '_cumsum.raw', dtype=float, mode='w+',
            shape=(steps,) + enderlein_image.shape)
        processed_frames = numpy.memmap(
            basename + '_frames.raw', dtype=float, mode='w+',
            shape=(steps,) + enderlein_image.shape)
        confocal_image = numpy.zeros_like(enderlein_image)
    enderlein_normalization += 1e-12
    image_data = array_illumination.load_image_data(data_filename, xPix, yPix, zPix)
    aperture = gaussian(2*window_footprint+1, std=aperture_size
                        ).reshape(2*window_footprint+1, 1)
    aperture = aperture * aperture.T
    grid_step_x = new_grid_x[1] - new_grid_x[0]
    grid_step_y = new_grid_y[1] - new_grid_y[0]
    subgrid_footprint = numpy.floor(
        (-1 + window_footprint * 0.5 / grid_step_x,
         -1 + window_footprint * 0.5 / grid_step_y))
    subgrid = ( #Add 2*(r_0 - r_M) to this to get s_desired
        window_footprint + 2 * grid_step_x * numpy.arange(
            -subgrid_footprint[0], subgrid_footprint[0] + 1),
        window_footprint + 2 * grid_step_y * numpy.arange(
            -subgrid_footprint[1], subgrid_footprint[1] + 1))
    subgrid_points = (2*subgrid_footprint[0] + 1) * (2*subgrid_footprint[1] + 1)
    for z in range(steps):
        this_frames_image.fill(0.)
        this_frames_normalization.fill(1e-12)
        if verbose:
            sys.stdout.write("\rProcessing raw data image %i"%(z))
            sys.stdout.flush()
        lattice_points, i_list, j_list = array_illumination.generate_lattice(
            image_shape=(xPix, yPix),
            lattice_vectors=lattice_vectors,
            center_pix=offset_vector + array_illumination.get_shift(
                shift_vector, z),
            edge_buffer=window_footprint+1,
            return_i_j=True)
        for m, lp in enumerate(lattice_points):
            i, j = int(i_list[m]), int(j_list[m])
            """Take an image centered on each illumination point"""
            spot_image = array_illumination.get_centered_subimage(
                center_point=lp, window_size=window_footprint,
                image=image_data[z, :, :], background=background_frame)
            """Aperture the image with a synthetic pinhole"""
            intensity_normalization = 1.0 / intensities_vs_galvo_position.get(
                (i, j), {}).get(z, numpy.inf)
            if (intensity_normalization == 0 or
                spot_image.shape != (2*window_footprint+1, 2*window_footprint+1)
                ):
                continue #Skip to the next spot
            apertured_image = aperture * spot_image * intensity_normalization
            """Smooth and resample the apertured image"""
            gaussian_filter(apertured_image, sigma=smoothing_sigma,
                            output=apertured_image)
            nearest_grid_point = numpy.round(
                (lp - (new_grid_x[0], new_grid_y[0])) /
                (grid_step_x, grid_step_y))
            new_coordinates = numpy.meshgrid(
                subgrid[0] + 2 * (nearest_grid_point[0] - lp[0]),
                subgrid[1] + 2 * (nearest_grid_point[1] - lp[1]))
            resampled_image = interpolation.map_coordinates(
                apertured_image,
                (new_coordinates[0].reshape(subgrid_points),
                 new_coordinates[1].reshape(subgrid_points))
                ).reshape(2*subgrid_footprint[0]+1, 2*subgrid_footprint[1]+1).T
            """Add the recentered image back to the scan grid"""
            if intensity_normalization > 0:
                this_frames_image[
                    nearest_grid_point[0]-subgrid_footprint[0]:
                    nearest_grid_point[0]+subgrid_footprint[0]+1,
                    nearest_grid_point[1]-subgrid_footprint[1]:
                    nearest_grid_point[1]+subgrid_footprint[1]+1,
                    ] += resampled_image
                this_frames_normalization[
                    nearest_grid_point[0]-subgrid_footprint[0]:
                    nearest_grid_point[0]+subgrid_footprint[0]+1,
                    nearest_grid_point[1]-subgrid_footprint[1]:
                    nearest_grid_point[1]+subgrid_footprint[1]+1,
                    ] += 1
                if intermediate_data:
                    confocal_image[
                        nearest_grid_point[0]-window_footprint:
                        nearest_grid_point[0]+window_footprint+1,
                        nearest_grid_point[1]-window_footprint:
                        nearest_grid_point[1]+window_footprint+1
                        ] += interpolation.shift(
                            apertured_image, shift=(lp-nearest_grid_point))
            if show_steps:
                pylab.clf()
                pylab.suptitle(
                    "Spot %i, %i in frame %i\nCentered at %0.2f, %0.2f\n"%(
                        i, j, z, lp[0], lp[1]) + (
                            "Nearest grid point: %i, %i"%(
                                nearest_grid_point[0], nearest_grid_point[1])))
                pylab.subplot(1, 3, 1)
                pylab.imshow(
                    spot_image, interpolation='nearest', cmap=pylab.cm.gray)
                pylab.subplot(1, 3, 2)
                pylab.imshow(
                    apertured_image, interpolation='nearest', cmap=pylab.cm.gray)
                pylab.subplot(1, 3, 3)
                pylab.imshow(
                    resampled_image, interpolation='nearest', cmap=pylab.cm.gray)
                fig.show()
                fig.canvas.draw()
                response = raw_input('\nHit enter to continue, q to quit:')
                if response == 'q' or response == 'e' or response == 'x':
                    print "Done showing steps..."
                    show_steps = False
        enderlein_image += this_frames_image
        enderlein_normalization += this_frames_normalization
        ###Temporary hack:
        enderlein_normalization.fill(1)
        this_frames_normalization.fill(1)
        if intermediate_data:
            cumulative_sum[z, :, :] = (
                enderlein_image * 1. / enderlein_normalization)
            processed_frames[
                z, :, :] = this_frames_image * 1. / this_frames_normalization
        if show_slices:
            pylab.clf()
            pylab.imshow(enderlein_image * 1.0 / enderlein_normalization,
                         cmap=pylab.cm.gray, interpolation='nearest')
            fig.show()
            fig.canvas.draw()
            response=raw_input('Hit enter to continue...')

    enderlein_image = enderlein_image * 1.0 / enderlein_normalization
    enderlein_image.tofile(enderlein_image_name)
    if intermediate_data:
        confocal_image.tofile(basename + '_confocal.raw')
fig = pylab.figure()
pylab.imshow(enderlein_image,
             interpolation='nearest', cmap=pylab.cm.gray)
pylab.colorbar()
fig.show()
