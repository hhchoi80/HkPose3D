using UnityEngine;
using System.IO;
using System.Text;
using System;

namespace ReadyPlayerMe.Samples.QuickStart
{
    [RequireComponent(typeof(ThirdPersonMovement), typeof(PlayerInput))]
    public class ThirdPersonController : MonoBehaviour
    {
        private const float FALL_TIMEOUT = 0.15f;
        private static readonly int MoveSpeedHash = Animator.StringToHash("MoveSpeed");
        private static readonly int JumpHash = Animator.StringToHash("JumpTrigger");
        private static readonly int FreeFallHash = Animator.StringToHash("FreeFall");
        private static readonly int IsGroundedHash = Animator.StringToHash("IsGrounded");

        private Transform playerCamera;
        private Animator animator;
        private Vector2 inputVector;
        private Vector3 moveVector;
        private GameObject avatar;
        private ThirdPersonMovement thirdPersonMovement;
        private PlayerInput playerInput;

        private float fallTimeoutDelta;
        private float captureTimer;  // Timer to track the capture interval
        private bool isInitialized;

        [SerializeField][Tooltip("Useful to toggle input detection in editor")]
        private bool inputEnabled = true;
        [SerializeField][Tooltip("Enable saving of 3D pose Ground Truth files")]
        private bool GT_fileSaveEnabled = false; // 파일 저장 활성화 여부
        [SerializeField][Tooltip("Time Interval for saving 3D Pose Ground Truth files")]
        private float captureInterval = 0.5f; // 캡처 간격        

        private void Init()
        {
            thirdPersonMovement = GetComponent<ThirdPersonMovement>();
            playerInput = GetComponent<PlayerInput>();
            playerInput.OnJumpPress += OnJump;
            isInitialized = true;

            Directory.CreateDirectory(Path.Combine("Captures", "BodyPos3dGT")); // Ensure directory exists
        }

        public void Setup(GameObject target, RuntimeAnimatorController runtimeAnimatorController)
        {
            if (!isInitialized)
            {
                Init();
            }

            avatar = target;
            thirdPersonMovement.Setup(avatar);
            animator = avatar.GetComponent<Animator>();
            animator.runtimeAnimatorController = runtimeAnimatorController;
            animator.applyRootMotion = false;
        }

        private void Update()
        {
            if (avatar == null)
            {
                return;
            }
            if (inputEnabled)
            {
                playerInput.CheckInput();
                var xAxisInput = playerInput.AxisHorizontal;
                var yAxisInput = playerInput.AxisVertical;
                thirdPersonMovement.Move(xAxisInput, yAxisInput);
                thirdPersonMovement.SetIsRunning(playerInput.IsHoldingLeftShift);
            }
            UpdateAnimator();

            // by HHCHOI
            if (Input.GetKeyDown(KeyCode.Alpha1))
            {
                animator.SetTrigger("TPoseTrigger");
            }            
            if (Input.GetKeyDown(KeyCode.Alpha2))
            {
                animator.SetTrigger("TalkingVar3Trigger");
            }           
            if (Input.GetKeyDown(KeyCode.Alpha3))
            {
                animator.SetTrigger("FallingDownTrigger");      // 뒤로 넘어짐
            }                     
            if (Input.GetKeyDown(KeyCode.Alpha4))
            {
                animator.SetTrigger("KnockedOutTrigger");       // 앞으로 넘어짐
            }            
            if (Input.GetKeyDown(KeyCode.Alpha5))
            {
                animator.SetTrigger("HitByCarTrigger");         // 옆으로 넘어짐
            }            
            if (Input.GetKeyDown(KeyCode.Alpha6))
            {
                animator.SetTrigger("KnockedDownTrigger");      // 뒤->앞으로 넘어짐
            }
            if (Input.GetKeyDown(KeyCode.Q))
            {
                animator.SetTrigger("BackToIdleTrigger");
            }
        }

        private void LateUpdate()
        {
            if (GT_fileSaveEnabled)
            {
                captureTimer += Time.deltaTime;

                if (captureTimer >= captureInterval)
                {
                    captureTimer = 0f;  // Reset the timer

                    DateTime currTime = System.DateTime.Now;
                    string exactTimeStamp = currTime.ToString("yyyy-MM-dd_HH-mm-ss.fff");
                    string slottedMilliseconds = currTime.Millisecond < (captureInterval*1000) ? "0" : "5";
                    string slottedTimeStamp = currTime.ToString("yyyy-MM-dd_HH-mm-ss") + "." + slottedMilliseconds;

                    // 파일 경로 생성
                    string bodyPosFilePath = Path.Combine("Captures", "BodyPos3dGT", $"body_pos3D_{slottedTimeStamp}.txt");

                    StringBuilder positions = new StringBuilder();
                    AppendBodyPartPosition("Head", positions);  // Nose
                    AppendBodyPartPosition("LeftEye", positions);
                    AppendBodyPartPosition("RightEye", positions);
                    // AppendBodyPartPosition("LeftEye", positions);  // LeftEar는 생략
                    // AppendBodyPartPosition("RightEye", positions); // RightEar는 생략
                    AppendBodyPartPosition("LeftArm", positions);
                    AppendBodyPartPosition("RightArm", positions);
                    AppendBodyPartPosition("LeftForeArm", positions);
                    AppendBodyPartPosition("RightForeArm", positions);
                    AppendBodyPartPosition("LeftHand", positions);
                    AppendBodyPartPosition("RightHand", positions);
                    AppendBodyPartPosition("LeftUpLeg", positions);
                    AppendBodyPartPosition("RightUpLeg", positions);
                    AppendBodyPartPosition("LeftLeg", positions);
                    AppendBodyPartPosition("RightLeg", positions);
                    AppendBodyPartPosition("LeftFoot", positions);
                    AppendBodyPartPosition("RightFoot", positions);
                    positions.AppendLine($"{exactTimeStamp}");      // 측정 시간 정보 추가

                    File.WriteAllText(bodyPosFilePath, positions.ToString());
                    print($"Captured body positions to {bodyPosFilePath}");
                }
            }            
        }

        private void AppendBodyPartPosition(string bodyPartName, StringBuilder positions)
        {
            GameObject bodyPart = GameObject.Find(bodyPartName);
            if (bodyPart != null)
            {
                Vector3 position = bodyPart.transform.position;
                positions.AppendLine($"{position.x}, {position.y}, {position.z}");
            }
            else
            {
                positions.AppendLine($"{bodyPartName}: na, na, na");
            }
        }

        private void UpdateAnimator()
        {
            var isGrounded = thirdPersonMovement.IsGrounded();
            animator.SetFloat(MoveSpeedHash, thirdPersonMovement.CurrentMoveSpeed);
            animator.SetBool(IsGroundedHash, isGrounded);
            if (isGrounded)
            {
                fallTimeoutDelta = FALL_TIMEOUT;
                animator.SetBool(FreeFallHash, false);
            }
            else
            {
                if (fallTimeoutDelta >= 0.0f)
                {
                    fallTimeoutDelta -= Time.deltaTime;
                }
                else
                {
                    animator.SetBool(FreeFallHash, true);
                }
            }
        }

        private void OnJump()
        {
            if (thirdPersonMovement.TryJump())
            {
                animator.SetTrigger(JumpHash);
            }
        }
    }
}
