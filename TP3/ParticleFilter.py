"""
TP particle filter for mobile robots localization

authors: Goran Frehse, David Filliat, Nicolas Merlinge
"""

from math import sin, cos, atan2, pi
import matplotlib as mpl 
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq
seed = 123456
np.random.seed(seed)

import os
try:
    os.makedirs("outputs")
except:
    pass

# ---- Simulator class (world, control and sensors) ----

class Simulation:
    def __init__(self, Tf, dt_pred, xTrue, QTrue, xOdom, Map, RTrue, dt_meas):
        self.Tf = Tf
        self.dt_pred = dt_pred
        self.nSteps = int(np.round(Tf/dt_pred))
        self.QTrue = QTrue
        self.xTrue = xTrue
        self.xOdom = xOdom
        self.Map = Map
        self.RTrue = RTrue
        self.dt_meas = dt_meas
        
    # return true control at step k
    def get_robot_control(self, k):
        # generate  sin trajectory
        u = np.array([[0, 0.025,  0.1*np.pi / 180 * sin(3*np.pi * k / self.nSteps)]]).T
        return u
    
    
    # simulate new true robot position
    def simulate_world(self, k):
        dt_pred = self.dt_pred
        u = self.get_robot_control(k)
        self.xTrue = tcomp(self.xTrue, u, dt_pred)
        self.xTrue[2, 0] = angle_wrap(self.xTrue[2, 0])
    
    
    # computes and returns noisy odometry
    def get_odometry(self, k):
        # Ensuring random repetability for given k
        np.random.seed(seed*2 + k)
        
        # Model
        dt_pred = self.dt_pred
        u = self.get_robot_control(k)
        xnow = tcomp(self.xOdom, u, dt_pred)
        uNoise = np.sqrt(self.QTrue) @ np.random.randn(3)
        uNoise = np.array([uNoise]).T
        xnow = tcomp(xnow, uNoise, dt_pred)
        self.xOdom = xnow
        u_tilda = u + dt_pred*uNoise
        return xnow, u_tilda


    # generate a noisy observation of a random feature
    def get_observation(self, k):
        # Ensuring random repetability for given k
        np.random.seed(seed*3 + k)

        # Model
        if k*self.dt_pred % self.dt_meas == 0:
            notValidCondition = False # False: measurement valid / True: measurement not valid
            #Q6
            '''
            if 250 <= k*self.dt_pred <= 350:
                notValidCondition = True
            '''
            if notValidCondition:
                z = None
                iFeature = None
            else:
                iFeature = np.random.randint(0, self.Map.shape[1] - 1)
                zNoise = np.sqrt(self.RTrue) @ np.random.randn(2)
                zNoise = np.array([zNoise]).T
                z = observation_model(self.xTrue, iFeature, self.Map) + zNoise
                z[1, 0] = angle_wrap(z[1, 0])
        else:
            z = None
            iFeature = None
        return [z, iFeature]



# ---- Particle Filter: model functions ----


# evolution model (f)
def motion_model(x, u_tilda, dt_pred, QEst):
    # x: estimated state (x, y, heading)
    # u_tilda: noised control input (Vx, Vy, angular rate)
    
    x_pos, y_pos, theta = x[0, 0], x[1, 0], x[2, 0]
    Vx, Vy, omega = u_tilda[0, 0], u_tilda[1, 0], u_tilda[2, 0]
    w_k = np.random.multivariate_normal([0, 0, 0], QEst)
    
    # Update positions using alpha and beta
    xPred = np.array([[x_pos + (Vx + w_k[0]) * cos(theta) * dt_pred - (Vy + w_k[1]) * sin(theta) * dt_pred],
                       [y_pos + (Vx + w_k[0]) * sin(theta) * dt_pred + (Vy + w_k[1]) * cos(theta) * dt_pred],
                       [angle_wrap(theta) + (omega + w_k[2]) * dt_pred]])
    return xPred


# observation model (h)
def observation_model(xVeh, iFeature, Map):
    # xVeh: vehicle state
    # iFeature: observed feature index
    # Map: map of all features
    
    # Extract vehicle state
    x_veh, y_veh, theta_veh = xVeh[0, 0], xVeh[1, 0], xVeh[2, 0]
    
    # Extract feature position
    x_feat, y_feat = Map[0, iFeature], Map[1, iFeature]
    
    dx = x_feat - x_veh
    dy = y_feat - y_veh
    range_ = np.sqrt(dx**2 + dy**2)
    bearing = atan2(dy, dx) - theta_veh
    bearing = angle_wrap(bearing)

    z = np.array([[range_], [bearing]])
    return z


# ---- particle filter implementation ----

# Particle filter resampling
def re_sampling(px, pw):
    """
    low variance re-sampling
    """

    w_cum = np.cumsum(pw)
    base = np.arange(0.0, 1.0, 1 / nParticles)
    re_sample_id = base + np.random.uniform(0, 1 / nParticles)
    indexes = []
    ind = 0
    for ip in range(nParticles):
        while re_sample_id[ip] > w_cum[ind]:
            ind += 1
        indexes.append(ind)

    px = px[:, indexes]
    # pw = pw[indexes]
    
    # Normalization
    pw = np.ones(pw.shape)
    pw = pw / np.sum(pw)

    return px, pw

def reallocation_resampling(particles, weights):
    M = weights.shape[0]
    N = nParticles
    n = 0
    resampled_particles = []
    resampled_weights = []

    for m in range(M):
        # Check the weight condition
        if weights[m] >= 1 / N:
            N_m_t = int(np.floor(N * weights[m]))  # Calculate how many particles to copy
            for h in range(N_m_t):
                n += 1
                resampled_particles.append(particles[:, m])  # Copy the particle
                resampled_weights.append(weights[m] / N_m_t)  # Normalize the weight
        else:
            u = np.random.uniform(0, 1 / N)  # Sample from uniform distribution
            if weights[m] >= u:
                n += 1
                resampled_particles.append(particles[:, m])  # Copy the particle
                resampled_weights.append(1 / N)  # Weight is uniform

    while len(resampled_particles) < N:
        idx = np.random.choice(M)
        resampled_particles.append(particles[:, idx])
        resampled_weights.append(1 / N)

    resampled_particles = np.array(resampled_particles).T
    resampled_weights = np.array(resampled_weights)
    
    return resampled_particles, resampled_weights


# ---- Utils functions ----

# Init displays
show_animation = True
f, (ax1, ax2) = plt.subplots(1, 2, sharey=True, figsize=(14, 7))
ax3 = plt.subplot(3, 2, 2)
ax4 = plt.subplot(3, 2, 4)
ax5 = plt.subplot(3, 2, 6)


# fit angle between -pi and pi
def angle_wrap(a):
    if (a > np.pi):
        a = a - 2 * pi
    elif (a < -np.pi):
        a = a + 2 * pi
    return a


# composes two transformations
def tcomp(tab, tbc, dt):
    assert tab.ndim == 2 # eg: robot state [x, y, heading]
    assert tbc.ndim == 2 # eg: robot control [Vx, Vy, angle rate]
    #dt : time-step (s)

    angle = tab[2, 0] + dt * tbc[2, 0] # angular integration by Euler

    angle = angle_wrap(angle)
    s = sin(tab[2, 0])
    c = cos(tab[2, 0])
    position = tab[0:2] + dt * np.array([[c, -s], [s, c]]) @ tbc[0:2] # position integration by Euler
    out = np.vstack((position, angle))

    return out


def plotParticles(simulation, k, iFeature, hxTrue, hxOdom, hxEst, hxError, hxSTD, htime, save = True):
    # simulation : Simulation object (containing world simulation and sensors)
    # k : current time-step
    # iFeature : index of current emitting amer 
    # hxTrue : true trajectory
    # hxOdom : odometric trajectory
    # hxEst : estimated trajectory
    # hxError : error (basically "hxEst - hxTrue")
    # hxSTD : standard deviation on estimate
    # save : True to save a figure as an image
        
    # for stopping simulation with the esc key.
    times = np.stack(htime)
    plt.gcf().canvas.mpl_connect('key_release_event',
                lambda event: [exit(0) if event.key == 'escape' else None])

    ax1.cla()

    # Plot true landmark and trajectory
    ax1.plot(simulation.Map[0, :], simulation.Map[1, :], "*k")
    ax1.plot(hxTrue[0, :], hxTrue[1, :], "-k", label="True")
    if iFeature != None: ax1.plot([simulation.xTrue[0][0], simulation.Map[0, iFeature]], [simulation.xTrue[1][0], simulation.Map[1, iFeature]], "-b")

    # Plot odometry trajectory
    ax1.plot(hxOdom[0, :], hxOdom[1, :], "-g", label="Odom")

    # Plot estimated trajectory and current particles
    ax1.plot(hxEst[0, :], hxEst[1, :], "-r", label="Part. Filt.")
    ax1.plot(xEst[0], xEst[1], ".r")
    ax1.scatter(xParticles[0, :], xParticles[1, :], s=wp*10)
    for i in range(nParticles):
        ax1.arrow(xParticles[0, i], xParticles[1, i], 5*np.cos(xParticles[2, i]+np.pi/2), 5*np.sin(xParticles[2, i]+np.pi/2), color = 'orange')

    ax1.axis([-60, 60, -60, 60])
    ax1.grid(True)
    ax1.legend()

    #Q6
    '''
    ax1.axvline(x=250, color='g', linestyle='--', label='t = 250 s')
    ax1.axvline(x=350, color='g', linestyle='--', label='t = 350 s')
    '''

    # plot errors curves
    ax3.plot(times, hxError[0, :], 'b')
    ax3.plot(times,  3.0 * hxSTD[0, :], 'r')
    ax3.plot(times, - 3.0 * hxSTD[0, :], 'r')
    ax3.grid(True)
    ax3.set_ylabel('x (m)')
    ax3.set_xlabel('time (s)')
    ax3.set_title(r'Real error (blue) and 3 $\sigma$ covariances (red)')

    ax4.plot(times, hxError[1, :], 'b')
    ax4.plot(times, 3.0 * hxSTD[1, :], 'r')
    ax4.plot(times, -3.0 * hxSTD[1, :], 'r')
    ax4.grid(True)
    ax4.set_ylabel('y (m)')
    ax5.set_xlabel('time (s)')

    ax5.plot(times, hxError[2, :], 'b')
    ax5.plot(times, 3.0 * hxSTD[2, :], 'r')
    ax5.plot(times, -3.0 * hxSTD[2, :], 'r')
    ax5.grid(True)
    ax5.set_ylabel(r"$\theta$ (rad)")
    ax5.set_xlabel('time (s)')

    if save: plt.savefig(r'outputs/SRL' + str(k) + '.png')
#        plt.pause(0.01)


# =============================================================================
# Main Program
# =============================================================================

# Enable/disable plotting
is_plot = True

# Nb of particle in the filter
nParticles = 300

# Simulation time
Tf = 1000       # final time (s)
dt_pred = 1     # Time between two dynamical predictions (s)
dt_meas = 1     # Time between two measurement updates (s)

# Location of landmarks
nLandmarks = 5
Map = 120*np.random.rand(2, nLandmarks)-60

# True covariance of errors used for simulating robot movements
QTrue = np.diag([0.02, 0.02, 1*pi/180]) ** 2
RTrue = np.diag([0.5, 1*pi/180]) ** 2

# Modeled errors used in the Particle filter process
QEst = 2 * np.eye(3, 3) @ QTrue
REst = 2 * np.eye(2, 2) @ RTrue

# initial conditions
xTrue = np.array([[1, -50, 0]]).T
#xTrue = np.array([[1, -40, -pi/2]]).T
xOdom = xTrue

# initial conditions: - a point cloud around truth
xParticles = xTrue + np.diag([1, 1, 0.1]) @ np.random.randn(3, nParticles)

# initial conditions: global localization
#xParticles = 120 * np.random.rand(3, nParticles)-60

# initial weights
wp = np.ones((nParticles))/nParticles
wp = wp / np.sum(wp)

# initial estimate
xEst = np.average(xParticles, axis=1, weights=wp)
xEst = np.expand_dims(xEst, axis=1)
xSTD = np.sqrt(np.average((xParticles-xEst)*(xParticles-xEst),
               axis=1, weights=wp))
xSTD = np.expand_dims(xSTD, axis=1)

# Init history matrixes
hxEst = xEst
hxTrue = xTrue
hxOdom = xOdom
err = xEst - xTrue
err[2, 0] = angle_wrap(err[2, 0])
hxError = err
hxSTD = xSTD
htime = [0]

# Simulation environment
simulation = Simulation(Tf, dt_pred, xTrue, QTrue, xOdom, Map, RTrue, dt_meas)

# histograma = []
cmap=mpl.colormaps["Wistia"] #Q4

if is_plot: plotParticles(simulation, 0, None, hxTrue, hxOdom, hxEst, hxError, hxSTD, htime, save = True)

# Temporal loop
for k in range(1, simulation.nSteps):
    htime.append(k*simulation.dt_pred)
#    print(k)
    # Simulate robot motion
    simulation.simulate_world(k)

    # Get odometry measurements
    xOdom, u_tilda = simulation.get_odometry(k)

    # do prediction
    # for each particle we add control vector AND noise
    for p in range(nParticles):
        xParticles[:, p:p+1] = motion_model(xParticles[:, p:p+1], u_tilda, simulation.dt_pred, QEst)
    # observe a random feature
    [z, iFeature] = simulation.get_observation(k)

    if z is not None:
        for p in range(nParticles):
            # Predict observation from the particle position
            zPred = observation_model(xParticles[:, p:p+1], iFeature, simulation.Map)

            # Innovation : perception error
            Innov = z - zPred
            Innov[1] = angle_wrap(Innov[1])

            # Compute particle weight using gaussian model
            wp[p] *= np.exp(-0.5 * Innov.T @ np.linalg.inv(REst) @ Innov).item()
    # Normalization
    wp /= np.sum(wp)

    #print("poids 1 = ", wp)
    
    
    # Compute position as weighted mean of particles
    xEst = np.average(xParticles, axis=1, weights=wp)
    xEst = np.expand_dims(xEst, axis=1)

    # Compute particles std deviation
    PEst = np.cov(xParticles, aweights=wp, ddof=0) # Empirical covariance matrix

    xSTD = np.sqrt(np.diag(PEst))  # Column vector of standard deviations (sqrt of diagonal of PEst)
    xSTD = np.expand_dims(xSTD, axis=1)


    theta_eff = 0.1
    Nth = nParticles * theta_eff
    Neff = 1.0 / np.sum(wp**2)  # Effective number of particles
    if Neff < Nth:
        # Particle resampling
        xParticles, wp = reallocation_resampling(xParticles, wp)
        # xParticles, wp = re_sampling(xParticles, wp)
        #print("poids 2 = ", wp)

    # store data history
    hxTrue = np.hstack((hxTrue, simulation.xTrue))
    hxOdom = np.hstack((hxOdom, simulation.xOdom))
    hxEst = np.hstack((hxEst, xEst))
    err = xEst - simulation.xTrue
    err[2, 0] = angle_wrap(err[2, 0])
    hxError = np.hstack((hxError, err))
    hxSTD = np.hstack((hxSTD, xSTD))

    # plot every 20 updates
    if is_plot and k*simulation.dt_pred % 20 == 0:
        plotParticles(simulation, k, iFeature, hxTrue, hxOdom, hxEst, hxError, hxSTD, htime, save = True)
    
    '''
    if is_plot and k*simulation.dt_pred % 100 == 0:
        hist, bins = np.histogram(wp, bins=100, range=(0.0, 0.05))
        histograma.append(hist)
    '''

plt.show()

tErrors = np.sqrt(np.square(hxError[0, :]) + np.square(hxError[1, :]))
print("Mean (var) translation error : {:e} ({:e})".format(np.mean(tErrors), np.var(tErrors)))
print("Press Q in figure to finish...")
plt.show()

'''
# Create a new figure for the histogram and colorbar
fig, ax = plt.subplots()

for i, hist in enumerate(histograma):
    ax.fill_between(bins[:-1], hist, alpha=(0.1 + 0.3 * hist / np.max(histograma)), color=cmap(i * 25))

# Set the title and labels
ax.set_title("Histogramme superposé des poids")
ax.set_xlabel("Poids")
ax.set_ylabel("Nombre de particules")

# Create a new axis for the colorbar
cbar_ax = fig.add_axes([0.92, 0.15, 0.03, 0.7])  # [left, bottom, width, height]

# Set the colorbar
norm = mpl.colors.Normalize(vmin=1, vmax=1000)
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm.set_array([])
fig.colorbar(sm, cax=cbar_ax, ticks=np.linspace(1, 1000, 11)).set_label('Iteración')

'''