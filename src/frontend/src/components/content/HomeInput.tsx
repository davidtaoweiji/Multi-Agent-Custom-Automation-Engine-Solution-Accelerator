import {
    Body1Strong,
    Button,
    Caption1,
    Text,
    Title2,
} from "@fluentui/react-components";

import React, { useRef, useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";

import "./../../styles/Chat.css";
import { getUserId, getUserInfoGlobal } from "../../api/config";
import { PlanDataService } from "../../services/PlanDataService";
import { APIService } from "../../api/apiService";
import "../../styles/prism-material-oceanic.css";
import "./../../styles/HomeInput.css";

import { HomeInputProps, iconMap, QuickTask } from "../../models/homeInput";
import { TaskService } from "../../services/TaskService";
import { NewTaskService } from "../../services/NewTaskService";
import { RAIErrorCard, RAIErrorData } from "../errors";
import { ImageUpload, ImageFile } from "../common/ImageUpload";

import ChatInput from "@/coral/modules/ChatInput";
import InlineToaster, { useInlineToaster } from "../toast/InlineToaster";
import PromptCard from "@/coral/components/PromptCard";
import { Send } from "@/coral/imports/bundleicons";
import { Clipboard20Regular } from "@fluentui/react-icons";

// Icon mapping function to convert string icons to FluentUI icons
const getIconFromString = (iconString: string | React.ReactNode): React.ReactNode => {
    // If it's already a React node, return it
    if (typeof iconString !== 'string') {
        return iconString;
    }

    return iconMap[iconString] || iconMap['default'] || <Clipboard20Regular />;
};

const truncateDescription = (description: string, maxLength: number = 180): string => {
    if (!description) return '';

    if (description.length <= maxLength) {
        return description;
    }


    const truncated = description.substring(0, maxLength);
    const lastSpaceIndex = truncated.lastIndexOf(' ');

    const cutPoint = lastSpaceIndex > maxLength - 20 ? lastSpaceIndex : maxLength;

    return description.substring(0, cutPoint) + '...';
};

// Extended QuickTask interface to store both truncated and full descriptions
interface ExtendedQuickTask extends QuickTask {
    fullDescription: string; // Store the full, untruncated description
}

const HomeInput: React.FC<HomeInputProps> = ({
    selectedTeam,
}) => {
    const [submitting, setSubmitting] = useState<boolean>(false);
    const [input, setInput] = useState<string>("");
    const [raiError, setRAIError] = useState<RAIErrorData | null>(null);
    const [simpleChatResponse, setSimpleChatResponse] = useState<string>("");
    const [simpleChatError, setSimpleChatError] = useState<string>("");
    const [isSimpleChatMode, setIsSimpleChatMode] = useState<boolean>(false);
    const [attachedImages, setAttachedImages] = useState<ImageFile[]>([]);
    const [chatHistory, setChatHistory] = useState<Array<{
        id: string, 
        message: string, 
        response: string, 
        state?: string,
        invoiceData?: any[], 
        timestamp: Date
    }>>([]);
    const chatContainerRef = useRef<HTMLDivElement>(null);

    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const navigate = useNavigate();
    const location = useLocation(); // ✅ location.state used to control focus
    const { showToast, dismissToast } = useInlineToaster();

    useEffect(() => {
        if (location.state?.focusInput) {
            textareaRef.current?.focus();
        }
    }, [location]);

    const resetTextarea = () => {
        setInput("");
        setRAIError(null); // Clear any RAI errors
        setAttachedImages([]); // Clear attached images
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto";
            textareaRef.current.focus();
        }
    };

    useEffect(() => {
        const cleanup = NewTaskService.addResetListener(resetTextarea);
        return cleanup;
    }, []);

    // Check if current team is SimpleChatAgent on mount and when team changes
    useEffect(() => {
        const checkTeamType = async () => {
            try {
                const userId = getUserInfoGlobal()?.user_id || getUserId();
                if (userId) {
                    const isSimpleChat = await PlanDataService.isSimpleChatTeam(userId);
                    setIsSimpleChatMode(isSimpleChat);
                }
            } catch (error) {
                console.error("Error checking team type:", error);
            }
        };
        checkTeamType();
    }, [selectedTeam]); // Re-check when team changes

    const handleSubmit = async () => {
        if (input.trim()) {
            setSubmitting(true);
            setRAIError(null); // Clear any previous RAI errors
            setSimpleChatError(""); // Clear any previous SimpleChatAgent errors
            setSimpleChatError(""); // Clear any previous SimpleChatAgent errors
            
            try {
                // Check if current team is SimpleChatAgent team
                const userId = getUserInfoGlobal()?.user_id || getUserId();
                const isSimpleChat = await PlanDataService.isSimpleChatTeam(userId);
                
                if (isSimpleChat) {
                    // SimpleChatAgent flow - direct response, no plan creation
                    let id = showToast("Processing your message...", "progress");
                    setIsSimpleChatMode(true);
                    
                    const userMessage = input.trim();
                    
                    try {
                        const apiService = new APIService();
                        // Get File objects from ImageFile array
                        const imageFiles = attachedImages.map(img => img.file);
                        const response = await apiService.sendSimpleChatMessage(userMessage, imageFiles);
                        
                        console.log("SimpleChatAgent response:", response);
                        
                        // Parse JSON response with state information
                        let displayResponse = response.response;
                        let invoiceData = null;
                        let currentState = null;
                        
                        try {
                            const jsonResponse = JSON.parse(response.response);
                            console.log("Parsed JSON response:", jsonResponse);
                            
                            if (jsonResponse.state && jsonResponse.message) {
                                // This is a structured response with state
                                currentState = jsonResponse.state;
                                displayResponse = jsonResponse.message;
                                
                                // Handle different data structures
                                if (jsonResponse.invoices && Array.isArray(jsonResponse.invoices)) {
                                    invoiceData = jsonResponse.invoices;
                                    console.log("Found invoices array:", invoiceData);
                                } else if (jsonResponse.invoice_data && Array.isArray(jsonResponse.invoice_data)) {
                                    invoiceData = jsonResponse.invoice_data;
                                    console.log("Found invoice_data array:", invoiceData);
                                } else if (jsonResponse.reimbursement_form) {
                                    // Single form data, convert to array
                                    invoiceData = [jsonResponse.reimbursement_form];
                                    console.log("Found reimbursement_form, converted to array:", invoiceData);
                                }
                                
                                console.log(`Received structured response - State: ${currentState}, Data count: ${invoiceData?.length || 0}`);
                            }
                        } catch (e) {
                            // Not JSON, use response as is
                            console.log("Received plain text response:", response.response);
                        }
                        
                        // Add to chat history
                        const newChatEntry = {
                            id: Date.now().toString(),
                            message: userMessage,
                            response: displayResponse,
                            state: currentState,
                            invoiceData: invoiceData, // Store invoice data if available
                            timestamp: new Date()
                        };
                        setChatHistory(prev => [...prev, newChatEntry]);
                        
                        setInput("");
                        setAttachedImages([]); // Clear attached files after successful submission
                        
                        if (textareaRef.current) {
                            textareaRef.current.style.height = "auto";
                        }
                        
                        showToast("Response received!", "success");
                        dismissToast(id);
                    } catch (simpleChatError: any) {
                        console.error("SimpleChatAgent error:", simpleChatError);
                        const errorMessage = simpleChatError?.message || "Failed to get response. Please try again.";
                        setSimpleChatError(errorMessage);
                        showToast(errorMessage, "error");
                        dismissToast(id);
                    }
                } else {
                    // Traditional multi-agent flow - create plan and navigate
                    let id = showToast("Creating a plan", "progress");

                    const response = await TaskService.createPlan(
                        input.trim(),
                        selectedTeam?.team_id
                    );
                    console.log("Plan created:", response);
                    console.log("Response processing_mode:", response.processing_mode);
                    console.log("Response response content:", response.response);
                    setInput("");

                    if (textareaRef.current) {
                        textareaRef.current.style.height = "auto";
                    }

                    if (response.plan_id && response.plan_id !== null) {
                        // Check if this is a direct Invoice workflow response (fallback)
                        if (response.processing_mode === 'invoice_workflow_direct' && response.response) {
                            showToast("Response received!", "success");
                            dismissToast(id);
                            
                            // Navigate to plan page and pass the direct response
                            navigate(`/plan/${response.plan_id}`, { 
                                state: { 
                                    directResponse: response.response,
                                    processingMode: 'invoice_workflow_direct'
                                }
                            });
                        } else {
                            // Traditional orchestration mode
                            showToast("Plan created!", "success");
                            dismissToast(id);
                            navigate(`/plan/${response.plan_id}`);
                        }
                    } else {
                        showToast("Failed to create plan", "error");
                        dismissToast(id);
                    }
                }
            } catch (error: any) {
                console.log("Error creating plan:", error);
                let errorMessage = "Unable to create plan. Please try again.";
                
                // Check if this is an RAI validation error
                try {
                    // errorDetail = JSON.parse(error);
                    errorMessage = error?.message || errorMessage;
                } catch (parseError) {
                    console.error("Error parsing error detail:", parseError);
                }

                showToast(errorMessage, "error");
            } finally {
                setSubmitting(false);
            }
        }
    };

    const handleQuickTaskClick = (task: ExtendedQuickTask) => {
        setInput(task.fullDescription);
        setRAIError(null); // Clear any RAI errors when selecting a quick task
        if (textareaRef.current) {
            textareaRef.current.focus();
        }
    };

    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto";
            textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
        }
    }, [input]);

    // Auto-scroll to bottom when new chat messages are added
    useEffect(() => {
        if (chatContainerRef.current) {
            chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
        }
    }, [chatHistory]);

    // Convert team starting_tasks to ExtendedQuickTask format
    const tasksToDisplay: ExtendedQuickTask[] = selectedTeam && selectedTeam.starting_tasks ?
        selectedTeam.starting_tasks.map((task, index) => {
            // Handle both string tasks and StartingTask objects
            if (typeof task === 'string') {
                return {
                    id: `team-task-${index}`,
                    title: task,
                    description: truncateDescription(task),
                    fullDescription: task, // Store the full description
                    icon: getIconFromString("📋")
                };
            } else {
                // Handle StartingTask objects
                const startingTask = task as any; // Type assertion for now
                const taskDescription = startingTask.prompt || startingTask.name || 'Task description';
                return {
                    id: startingTask.id || `team-task-${index}`,
                    title: startingTask.name || startingTask.prompt || 'Task',
                    description: truncateDescription(taskDescription),
                    fullDescription: taskDescription, // Store the full description
                    icon: getIconFromString(startingTask.logo || "📋")
                };
            }
        }) : [];

    return (
        <div className="home-input-container">
            <div className="home-input-content">
                <div className="home-input-center-content">
                    <div className="home-input-title-wrapper">
                        <Title2>How can I help?</Title2>
                    </div>

                    {/* Chat History for SimpleChatAgent mode */}
                    {isSimpleChatMode && chatHistory.length > 0 && (
                        <div 
                            ref={chatContainerRef}
                            style={{
                                marginBottom: '24px',
                                maxHeight: '400px',
                                overflowY: 'auto',
                                padding: '16px 0'
                            }}
                        >
                            {chatHistory.map((chat) => (
                                <div key={chat.id}>
                                    {/* User Message */}
                                    <div style={{
                                        maxWidth: '800px',
                                        margin: '0 auto 24px auto',
                                        padding: '0 24px',
                                        display: 'flex',
                                        alignItems: 'flex-start',
                                        gap: '16px',
                                        justifyContent: 'flex-end'
                                    }}>
                                        <div style={{
                                            flex: 1,
                                            maxWidth: 'calc(100% - 48px)',
                                            display: 'flex',
                                            flexDirection: 'column',
                                            alignItems: 'flex-end'
                                        }}>
                                            <div style={{
                                                backgroundColor: 'var(--colorBrandBackground)',
                                                color: 'white',
                                                padding: '12px 16px',
                                                borderRadius: '8px',
                                                fontSize: '14px',
                                                lineHeight: '1.5',
                                                wordWrap: 'break-word',
                                                maxWidth: '80%',
                                                alignSelf: 'flex-end'
                                            }}>
                                                {chat.message}
                                            </div>
                                        </div>
                                        <div style={{
                                            width: '32px',
                                            height: '32px',
                                            borderRadius: '50%',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            flexShrink: 0,
                                            backgroundColor: 'var(--colorBrandBackground)',
                                            color: 'white'
                                        }}>
                                            👤
                                        </div>
                                    </div>
                                    
                                    {/* Assistant Response */}
                                    <div style={{
                                        maxWidth: '800px',
                                        margin: '0 auto 32px auto',
                                        padding: '0 24px',
                                        display: 'flex',
                                        alignItems: 'flex-start',
                                        gap: '16px'
                                    }}>
                                        <div style={{
                                            width: '32px',
                                            height: '32px',
                                            borderRadius: '50%',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            flexShrink: 0,
                                            backgroundColor: 'var(--colorNeutralBackground3)'
                                        }}>
                                            🤖
                                        </div>
                                        <div style={{
                                            flex: 1,
                                            maxWidth: 'calc(100% - 48px)',
                                            display: 'flex',
                                            flexDirection: 'column',
                                            alignItems: 'flex-start'
                                        }}>
                                            <div style={{
                                                backgroundColor: 'var(--colorNeutralBackground2)',
                                                color: 'var(--colorNeutralForeground1)',
                                                padding: '12px 16px',
                                                borderRadius: '8px',
                                                fontSize: '14px',
                                                lineHeight: '1.5',
                                                wordWrap: 'break-word',
                                                maxWidth: '100%',
                                                alignSelf: 'flex-start',
                                                whiteSpace: 'pre-wrap'
                                            }}>
                                                {/* Show state badge if available */}
                                                {chat.state && (
                                                    <div style={{
                                                        backgroundColor: 'var(--colorBrandBackground)',
                                                        color: 'white',
                                                        padding: '4px 8px',
                                                        borderRadius: '4px',
                                                        fontSize: '12px',
                                                        fontWeight: '600',
                                                        marginBottom: '8px',
                                                        display: 'inline-block'
                                                    }}>
                                                        State: {chat.state}
                                                    </div>
                                                )}
                                                
                                                {chat.response}
                                                
                                                {/* Display invoice data if available */}
                                                {chat.invoiceData && chat.invoiceData.length > 0 && (
                                                    <div style={{ 
                                                        marginTop: '16px', 
                                                        padding: '16px',
                                                        backgroundColor: 'var(--colorNeutralBackground1)',
                                                        borderRadius: '8px',
                                                        border: '1px solid var(--colorNeutralStroke2)'
                                                    }}>
                                                        <Text size={400} weight="semibold" style={{ 
                                                            color: 'var(--colorBrandForeground1)',
                                                            marginBottom: '12px',
                                                            display: 'block'
                                                        }}>
                                                            📋 Invoice Data ({chat.invoiceData.length} item{chat.invoiceData.length > 1 ? 's' : ''})
                                                        </Text>
                                                        
                                                        {/* Table format for invoice data */}
                                                        <div style={{
                                                            backgroundColor: 'white',
                                                            borderRadius: '6px',
                                                            border: '1px solid var(--colorNeutralStroke1)',
                                                            overflow: 'hidden',
                                                            overflowX: 'auto'
                                                        }}>
                                                            <table style={{
                                                                width: '100%',
                                                                borderCollapse: 'collapse',
                                                                fontSize: '13px',
                                                                minWidth: '600px'
                                                            }}>
                                                                <thead>
                                                                    <tr style={{
                                                                        backgroundColor: 'var(--colorNeutralBackground2)',
                                                                        borderBottom: '1px solid var(--colorNeutralStroke2)'
                                                                    }}>
                                                                        {/* Create header from first invoice keys */}
                                                                        {chat.invoiceData[0] && Object.keys(chat.invoiceData[0]).map((key) => (
                                                                            <th key={key} style={{
                                                                                padding: '12px 14px',
                                                                                textAlign: 'left',
                                                                                fontWeight: '600',
                                                                                color: 'var(--colorNeutralForeground2)',
                                                                                textTransform: 'capitalize',
                                                                                borderRight: '1px solid var(--colorNeutralStroke2)',
                                                                                whiteSpace: 'nowrap'
                                                                            }}>
                                                                                {key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                                                                            </th>
                                                                        ))}
                                                                    </tr>
                                                                </thead>
                                                                <tbody>
                                                                    {chat.invoiceData.map((invoice, index) => (
                                                                        <tr key={index} style={{
                                                                            borderBottom: index < chat.invoiceData!.length - 1 ? '1px solid var(--colorNeutralStroke1)' : 'none',
                                                                            backgroundColor: index % 2 === 0 ? 'white' : 'var(--colorNeutralBackground1)'
                                                                        }}>
                                                                            {Object.entries(invoice).map(([key, value], cellIndex) => (
                                                                                <td key={key} style={{
                                                                                    padding: '12px 14px',
                                                                                    borderRight: cellIndex < Object.entries(invoice).length - 1 ? '1px solid var(--colorNeutralStroke2)' : 'none',
                                                                                    verticalAlign: 'top',
                                                                                    maxWidth: key === 'items' ? '200px' : '150px',
                                                                                    wordWrap: 'break-word',
                                                                                    overflow: 'hidden',
                                                                                    textOverflow: 'ellipsis'
                                                                                }}>
                                                                                    <span style={{
                                                                                        color: key === 'amount' || key === 'total_amount' ? 'var(--colorBrandForeground1)' : (value ? 'var(--colorNeutralForeground1)' : 'var(--colorNeutralForeground3)'),
                                                                                        fontStyle: value ? 'normal' : 'italic',
                                                                                        fontWeight: key === 'amount' || key === 'total_amount' ? '600' : 'normal'
                                                                                    }} title={String(value) || 'N/A'}>
                                                                                        {/* Format specific fields */}
                                                                                        {key === 'amount' || key === 'total_amount' ? 
                                                                                            (value ? `$${String(value)}` : 'N/A') :
                                                                                            (String(value) || 'N/A')
                                                                                        }
                                                                                    </span>
                                                                                </td>
                                                                            ))}
                                                                        </tr>
                                                                    ))}
                                                                </tbody>
                                                            </table>
                                                        </div>
                                                        
                                                        {/* Summary information */}
                                                        <div style={{
                                                            marginTop: '12px',
                                                            padding: '8px 12px',
                                                            backgroundColor: 'var(--colorBrandBackground)',
                                                            color: 'white',
                                                            borderRadius: '4px',
                                                            fontSize: '12px',
                                                            textAlign: 'center'
                                                        }}>
                                                            Total: {chat.invoiceData.length} invoice{chat.invoiceData.length > 1 ? 's' : ''} processed
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Show error if present */}
                    {simpleChatError && (
                        <div style={{
                            marginBottom: '16px',
                            padding: '12px',
                            backgroundColor: '#fef2f2',
                            borderRadius: '6px',
                            border: '1px solid #fecaca',
                            color: '#dc2626'
                        }}>
                            <Text size={300}>Error: {simpleChatError}</Text>
                        </div>
                    )}

                    {/* Image Upload Component - only show in SimpleChatAgent mode */}
                    {isSimpleChatMode && (
                        <ImageUpload 
                            files={attachedImages}
                            onFilesChange={setAttachedImages}
                            maxFiles={5}
                        />
                    )}

                    <ChatInput
                        ref={textareaRef} // forwarding
                        value={input}
                        placeholder="Tell us what needs planning, building, or connecting—we'll handle the rest."
                        onChange={setInput}
                        onEnter={handleSubmit}
                        disabledChat={submitting}
                    >
                        <Button
                            appearance="subtle"
                            className="home-input-send-button"
                            onClick={handleSubmit}
                            disabled={submitting}
                            icon={<Send />}
                        />
                    </ChatInput>

                    <InlineToaster />

                    {/* Quick tasks section - only show when not in SimpleChatAgent mode */}
                    {!isSimpleChatMode && (
                        <div className="home-input-quick-tasks-section">
                            {tasksToDisplay.length > 0 && (
                                <>
                                    <div className="home-input-quick-tasks-header">
                                        <Body1Strong>Quick tasks</Body1Strong>
                                    </div>

                                    <div className="home-input-quick-tasks">
                                        <div>
                                            {tasksToDisplay.map((task) => (
                                                <PromptCard
                                                    key={task.id}
                                                    title={task.title}
                                                    icon={task.icon}
                                                    description={task.description}
                                                    onClick={() => handleQuickTaskClick(task)}
                                                    disabled={submitting}
                                                />
                                            ))}
                                        </div>
                                    </div>
                                </>
                            )}
                            {tasksToDisplay.length === 0 && selectedTeam && (
                                <div style={{
                                    textAlign: 'center',
                                    padding: '32px 16px',
                                    color: '#666'
                                }}>
                                    <Caption1>No starting tasks available for this team</Caption1>
                                </div>
                            )}
                            {!selectedTeam && (
                                <div style={{
                                    textAlign: 'center',
                                    padding: '32px 16px',
                                    color: '#666'
                                }}>
                                    <Caption1>Select a team to see available tasks</Caption1>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default HomeInput;