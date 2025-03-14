import os
import numpy as np

# Define the directory and file prefixes
CAM_DIR = os.path.join("..", "HkPose3D_Unity", "Captures") 
CAMERA_NAMES = ["Camera1", "Camera2", "Camera3", "Camera4"]
pos3D_prefix_template = "body_pos3D_"
pos2D_prefix_template = "{}_yolov8x-pose_"

def load_txt_files_sorted_by_time(directory, prefix):
    # Get all files in the directory with the specified prefix
    files = [f for f in os.listdir(directory) if f.startswith(prefix) and f.endswith(".txt")]
    
    # Sort the files by their last modified time
    files.sort(key=lambda f: os.path.getmtime(os.path.join(directory, f)))

    # Load the first 15 lines of each file into a list of np.arrays
    data_list = []
    for file in files:
        file_path = os.path.join(directory, file)
        
        # Open the file and read the first 15 lines
        with open(file_path, 'r') as f:
            lines = f.readlines()[:15]  # Read only the first 15 lines

        # Convert the read lines to a numpy array
        data = np.loadtxt(lines, delimiter=',')
        data_list.append(data)
    
    # Concatenate all arrays into a single np.array
    combined_data = np.vstack(data_list)
    
    return combined_data

def estimate_camera_matrix(object_points, image_points):
    """
    Estimate the camera projection matrix using DLT algorithm.

    Parameters:
    object_points (np.array): 3D object points of shape (N, 3).
    image_points (np.array): 2D image points of shape (N, 2).

    Returns:
    np.array: The 3x4 camera projection matrix.
    """
    num_points = object_points.shape[0]
    A = []

    for i in range(num_points):
        X, Y, Z = object_points[i]
        u, v = image_points[i]
        A.append([-X, -Y, -Z, -1, 0, 0, 0, 0, u*X, u*Y, u*Z, u])
        A.append([0, 0, 0, 0, -X, -Y, -Z, -1, v*X, v*Y, v*Z, v])

    A = np.array(A)
    U, S, Vt = np.linalg.svd(A)
    P = Vt[-1].reshape(3, 4)
    
    return P

def project_point(P, point_3d):
    """
    Project a 3D point onto the 2D image plane using the camera projection matrix.

    Parameters:
    P (np.array): The 3x4 camera projection matrix.
    point_3d (np.array): The 3D point as a numpy array of shape (3,).

    Returns:
    np.array: The 2D point on the image plane as a numpy array of shape (2,).
    """
    # Convert the 3D point to homogeneous coordinates (4D vector)
    point_3d_homogeneous = np.append(point_3d, 1)

    # Apply the camera projection matrix to the 3D point
    point_2d_homogeneous = np.dot(P, point_3d_homogeneous)

    # Convert from homogeneous coordinates to 2D coordinates
    u = point_2d_homogeneous[0] / point_2d_homogeneous[2]
    v = point_2d_homogeneous[1] / point_2d_homogeneous[2]

    return np.array([u, v])

# Iterate over all camera names
for camera_name in CAMERA_NAMES:
    calibration_dir = os.path.join(CAM_DIR, camera_name, "calibration")
    pos3D_prefix = pos3D_prefix_template
    pos2D_prefix = pos2D_prefix_template.format(camera_name)

    # Load and print the combined data for body_pos3D_
    pos3D_GT = load_txt_files_sorted_by_time(calibration_dir, pos3D_prefix)
    print(f"Combined body_pos3D_ data for {camera_name}:")
    print(pos3D_GT)

    # Load and print the combined data for Camera_ScreenShot_
    pos2D_xyc = load_txt_files_sorted_by_time(calibration_dir, pos2D_prefix)
    print(f"\nCombined {camera_name}_ScreenShot_ data:")
    print(pos2D_xyc)

    # Extract the first and second columns from pos2D_xyc and store it in pos2D_xy
    pos2D_xy = pos2D_xyc[:, :2]  # Extract the first and second columns

    # Print the pos2D_xy
    print(f"\nPose data (first and second columns of {camera_name}_ScreenShot_):")
    print(pos2D_xy)

    P = estimate_camera_matrix(pos3D_GT, pos2D_xy)
    print(f"Estimated camera projection matrix for {camera_name}:")
    print(P)

    # Save the matrix P to Camera_Pmatrix.txt
    output_file = os.path.join(calibration_dir, f"{camera_name}_Pmatrix_Est.txt")
    np.savetxt(output_file, P, delimiter=',', fmt='%0.6f')

    # Format and save the P matrix with the specified format
    with open(output_file, "w") as f:
        for row in P:
            f.write(", ".join(f"{value:.8e}" for value in row) + "\n")

    print(f"Camera projection matrix saved to {output_file}")

    ############################################################################
    ## pos3D_GT를 추정한 P matrix를 이용하여 2D로 projection하여 pos2D_xy와 비교 (MSE, RMSE)
    # Initialize an array to store the projected 2D points
    projected_2d_points = []

    # Loop through each 3D point and project it to 2D
    for point_3d in pos3D_GT:
        point_2d = project_point(P, point_3d)
        projected_2d_points.append(point_2d)

    # Convert the list of projected points to a numpy array (optional)
    projected_2d_points = np.array(projected_2d_points)

    # Output all 2D coordinates
    print(f"All projected 2D coordinates for {camera_name}:")
    print(projected_2d_points)

    # mse between pos2D_xy and projected_2d_points
    mse = np.mean(np.square(pos2D_xy - projected_2d_points))
    rmse = np.sqrt(mse)
    print(f"\nMSE & RMSE between pos2D_xy and projected_2d_points for {camera_name}: {mse:.6f}, {rmse:.6f} pixels")
